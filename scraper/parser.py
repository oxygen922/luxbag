"""HTML 解析器：列表页 + 详情页。

设计要点：
- 详情页按「区块」顺序解析（段落/小节标题/图片/图片网格/价格），
  忠实保留原文档的图文排版顺序，博客可按区块原样渲染。
- 解析阶段只产出【源站 URL】；图片转存到自有 CDN 由 storage 阶段统一替换。
"""
from __future__ import annotations

import re
from datetime import datetime
from bs4 import BeautifulSoup, NavigableString, Tag

from models import EntrySummary, Block


# ---------------- 列表页 ----------------

def parse_entry_id(href: str) -> str:
    """从 /entries/{id} 提取 id。"""
    m = re.search(r"/entries/([A-Za-z0-9]+)", href or "")
    return m.group(1) if m else ""


def parse_list_page(html: str, source: str, list_url: str, detail_base: str) -> list[EntrySummary]:
    """解析 today/feature 列表页，返回条目摘要列表（按出现顺序）。"""
    soup = BeautifulSoup(html, "lxml")
    out: list[EntrySummary] = []
    for li in soup.select("ul.grid-list > li"):
        a = li.select_one("a[href*='/entries/']")
        if not a:
            continue
        entry_id = parse_entry_id(a.get("href", ""))
        if not entry_id:
            continue
        title = (a.select_one("h3").get_text(strip=True)
                 if a.select_one("h3") else "")
        cover = ""
        thumb = a.select_one("span.thumb img")
        if thumb and thumb.get("src"):
            cover = thumb["src"]
        date_label = ""
        tip = a.select_one(".tip")
        if tip:
            date_label = tip.get_text(strip=True)
        likes = 0
        like = a.select_one(".like")
        if like:
            m = re.search(r"(\d+)", like.get_text())
            if m:
                likes = int(m.group(1))
        out.append(EntrySummary(
            entry_id=entry_id,
            title=title,
            source=source,
            source_url=f"{detail_base}{entry_id}",
            list_url=list_url,
            cover_url=cover,
            date_label=date_label,
            likes=likes,
        ))
    return out


def parse_pagination_last(html: str) -> int:
    """返回列表页最大页码（用于限流翻页）。"""
    soup = BeautifulSoup(html, "lxml")
    pages = [1]
    for a in soup.select("ul.ic-pagination a[href]"):
        m = re.search(r"page=(\d+)", a.get("href", ""))
        if m:
            pages.append(int(m.group(1)))
    return max(pages)


# ---------------- 详情页 ----------------

def _parse_date(label: str) -> tuple[str, str]:
    """'July 09, 2026' -> ('2026-07-09', 原标签)。解析失败则原样返回。"""
    label = (label or "").strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(label, fmt).date().isoformat(), label
        except ValueError:
            continue
    return "", label


def _img_https(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http://"):
        return "https://" + url[len("http://"):]
    if url.startswith("//"):
        return "https:" + url
    return url


def _upgrade_cover(url: str) -> str:
    """icitycdn 封面图末尾的 /WxH 限定缩略尺寸，改为 /0x0 取原图全分辨率。"""
    if not url:
        return url
    return re.sub(r"/\d+x\d+(?=[?]|$)", "/0x0", url)


_PROMO_PATTERNS = [
    re.compile(r"分享给(闺蜜|男友|朋友|男朋友|女朋友)"),
    re.compile(r"喜欢这个包包"),
    re.compile(r"专属壁纸"),
    re.compile(r"WALLPAPER\s+OF\s+IBAG", re.I),
    re.compile(r"获取.*壁纸"),
    re.compile(r"分享是一种美德"),
    re.compile(r"App\s*Store", re.I),
]


def _is_promo(text: str) -> bool:
    """识别源站固定推广块（分享 / 壁纸下载 / 应用引流）。"""
    if not text:
        return False
    return any(p.search(text) for p in _PROMO_PATTERNS)


def _scrub_text(text: str) -> str:
    """品牌替换：iBag / IBAG / ibag → KYNBAG（仅匹配连续的 iBag 整词，避免误伤 Mini Bag 等）。"""
    if not text:
        return text
    return re.sub(r"(?<!\w)iBag(?!\w)", "KYNBAG", text, flags=re.I)


def _grid_columns(div: Tag) -> int:
    for cls in div.get("class", []):
        m = re.match(r"grid_items_(\d+)", cls)
        if m:
            return int(m.group(1))
    container = div.select_one(".grid_container")
    if container:
        for cls in container.get("class", []):
            m = re.match(r"grid_items_(\d+)", cls)
            if m:
                return int(m.group(1))
        style = container.get("style", "")
        m = re.search(r"repeat\((\d+)", style)
        if m:
            return int(m.group(1))
        m = re.findall(r"1fr", style)
        if m:
            return len(m)
    return 2


def _inline_to_text(node) -> str:
    """把内联片段转成带 **加粗** 标记的纯文本。"""
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
        elif isinstance(child, Tag):
            if child.name == "br":
                parts.append("\n")
            elif child.name in ("strong", "b"):
                inner = child.get_text()
                if inner.strip():
                    parts.append(f"**{inner}**")
                else:
                    parts.append(inner)
            elif child.name in ("span", "em", "i", "a"):
                parts.append(child.get_text())
            else:
                parts.append(child.get_text())
    return "".join(parts)


def parse_detail_page(html: str) -> dict:
    """解析详情页，返回原始结构化数据（图片仍为源站 URL）。

    返回:
        {
          title, original_title, author, date_iso, date_label,
          cover_source, blocks: [Block, ...]
        }
    """
    soup = BeautifulSoup(html, "lxml")

    header = soup.select_one(".header") or soup
    title_el = header.select_one(".title")
    title = title_el.get_text(strip=True) if title_el else (soup.title.string if soup.title else "")
    author_el = header.select_one(".author")
    author = author_el.get_text(strip=True) if author_el else ""
    date_el = header.select_one(".date")
    date_label = date_el.get_text(strip=True) if date_el else ""
    date_iso, date_label = _parse_date(date_label)

    # 封面：取 og:image 并升级到 /0x0 原图全分辨率（避免 100x100 缩略图模糊）
    cover_source = ""
    og = soup.select_one('meta[property="og:image"]')
    if og and og.get("content"):
        cover_source = _upgrade_cover(_img_https(og["content"]))
    if not cover_source:
        pre = soup.select_one(".content.preContent .focusBox img")
        if pre and pre.get("src"):
            cover_source = _img_https(pre["src"])

    # 正文 content（排除 preContent）
    body = None
    for div in soup.select("div.content"):
        if "preContent" not in (div.get("class") or []):
            body = div
            break
    blocks: list[Block] = []
    if body is not None:
        blocks = _walk_body(body)

    # 后处理：剔除源站固定推广块（分享/壁纸/应用引流）与空块，统一品牌替换
    blocks = _postprocess_blocks(blocks)
    title = _scrub_text(title)
    author = _scrub_text(author)

    return {
        "title": title,
        "original_title": title,
        "author": author,
        "date_iso": date_iso,
        "date_label": date_label,
        "cover_source": cover_source,
        "blocks": blocks,
    }


def _postprocess_blocks(blocks: list[Block]) -> list[Block]:
    """剔除推广块/空块，对文本做品牌替换。"""
    out: list[Block] = []
    for b in blocks:
        if b.type in ("paragraph", "heading", "caption"):
            txt = _scrub_text(b.text or "")
            if not txt.strip() or _is_promo(txt):
                continue
            b.text = txt
        elif b.type == "image":
            if not (b.url or b.full_url):
                continue
        elif b.type == "grid":
            items = [it for it in b.items if it.get("url") or it.get("full_url")]
            if not items:
                continue
            b.items = items
        out.append(b)
    return out


def _flush_paragraphs(buf: list[str], blocks: list[Block]):
    """把累积的内联文本按空行切成段落区块。"""
    if not buf:
        return
    text = "".join(buf)
    # <br><br> => 段落分隔
    for para in re.split(r"\n{2,}", text):
        para = para.replace("\n", " ").strip()
        para = re.sub(r"\s+", " ", para)
        if para:
            blocks.append(Block(type="paragraph", text=para))


def _walk_body(body: Tag) -> list[Block]:
    """顺序遍历正文，产出区块，保留原文档排版顺序。"""
    blocks: list[Block] = []
    inline_buf: list[str] = []

    def flush():
        _flush_paragraphs(inline_buf, blocks)
        inline_buf.clear()

    for child in body.children:
        if isinstance(child, NavigableString):
            t = str(child)
            if t.strip():
                inline_buf.append(t)
            continue
        if not isinstance(child, Tag):
            continue

        name = child.name

        # 小节标题
        if name == "h2":
            flush()
            blocks.append(Block(type="heading", text=child.get_text(strip=True)))
            continue

        # 图片网格
        if name == "div" and "block_grid" in (child.get("class") or []):
            flush()
            columns = _grid_columns(child)
            items = []
            for gi in child.select(".grid_item"):
                a = gi.select_one("a[href]")
                img = gi.select_one("img[src]")
                price_span = gi.select_one("span")
                price = price_span.get_text(strip=True) if price_span else None
                items.append({
                    "url": _img_https(img["src"]) if img and img.get("src") else "",
                    "full_url": _img_https(a["href"]) if a and a.get("href") else "",
                    "price": price or "",
                })
            if items:
                blocks.append(Block(type="grid", columns=columns, items=items))
            continue

        # 价格说明
        if name == "div" and "caption" in (child.get("class") or []):
            flush()
            blocks.append(Block(type="caption", text=child.get_text(strip=True)))
            continue

        # 收尾的 focusBox（结束图），跳过
        if name == "div" and "focusBox" in (child.get("class") or []):
            flush()
            continue

        # 独立大图：<a href><img>（可能外层包了 span）
        if name == "a" and child.select_one("img[src]"):
            flush()
            img = child.select_one("img[src]")
            blocks.append(Block(type="image",
                                url=_img_https(img["src"]) if img.get("src") else "",
                                full_url=_img_https(child.get("href", ""))))
            continue
        if name == "span" and child.select_one("a[href] img[src]"):
            flush()
            a = child.select_one("a[href]")
            img = child.select_one("img[src]")
            blocks.append(Block(type="image",
                                url=_img_https(img["src"]) if img.get("src") else "",
                                full_url=_img_https(a.get("href", ""))))
            continue

        # 裸 img
        if name == "img" and child.get("src"):
            flush()
            blocks.append(Block(type="image", url=_img_https(child["src"])))
            continue

        # 内联文本（strong / 文本 / br 等）
        if name in ("strong", "b", "span", "em", "i"):
            inline_buf.append(_inline_to_text(child.parent if False else child))
            continue
        if name == "br":
            inline_buf.append("\n")
            continue

        # 其它块级（p, div 等）：取其文本参与段落
        txt = child.get_text(separator=" ", strip=True)
        if txt:
            inline_buf.append(txt + "\n\n")

    flush()
    return blocks
