"""博客文章 → DeepSeek 生成 Pin 文案 → Google Sheets → Cookie 发 Pin。

流程：
  1. 扫描 blog/content/articles/ 下所有文章 JSON
  2. 为每篇文章的封面 + 正文图片生成 Pinterest Pin 文案（DeepSeek）
  3. 将数据追加到 Google Sheets（跳过已同步的）
  4. 调用 Cookie 方式发布 Pin（board_id 从配置读取）

用法：
  python sync_pins.py                    # 全流程
  python sync_pins.py --dry-run          # 只生成文案、写入 Sheets，不发 Pin
  python sync_pins.py --sheets-only      # 只同步 Sheets
  python sync_pins.py --publish-only     # 只发 Pin（从 Sheets 读取未发布的）

环境变量（.env 或 GitHub Secrets）：
  DEEPSEEK_API_KEY       DeepSeek API Key
  GOOGLE_SHEET_ID        Google Sheet ID
  GOOGLE_SA_FILE         Service Account JSON 路径（默认 sa_credentials.json）
  PINTEREST_SESS         _pinterest_sess Cookie 值
  PINTEREST_PROXY        代理（可选）
  PINTEREST_BOARD_ID     默认画板 ID
  PINTEREST_BOARD_ID_2   第二个画板 ID（可选，交替使用）
  BLOG_BASE_URL          博客地址（默认 https://kynbag.blog）
  MAX_PINS_PER_RUN       每次运行最多发几个 Pin（默认 10）
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path

import requests

# 把父目录加入 path，以便引用 pinterest_client
SCRAPER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRAPER_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pinterest_client import PinterestCookieClient

try:
    import gspread
except ImportError:
    gspread = None


# ---------- 配置 ----------

ARTICLES_DIR = SCRAPER_DIR.parent / "blog" / "content" / "articles"
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_SA_FILE = os.getenv("GOOGLE_SA_FILE", str(SCRAPER_DIR / "sa_credentials.json"))
PINTEREST_SESS = os.getenv("PINTEREST_SESS", "")
PINTEREST_PROXY = os.getenv("PINTEREST_PROXY", "")
BOARD_IDS = [b for b in [os.getenv("PINTEREST_BOARD_ID", ""), os.getenv("PINTEREST_BOARD_ID_2", "")] if b]
BLOG_BASE_URL = os.getenv("BLOG_BASE_URL", "https://kynbag.com").rstrip("/")
MAX_PINS_PER_RUN = int(os.getenv("MAX_PINS_PER_RUN", "10"))
SHEET_HEADERS = ["board_id", "image_url", "title", "description", "link", "status", "article_id", "source"]


# ---------- DeepSeek ----------

def deepseek_generate_pin(article_title: str, excerpt: str, tags: list[str]) -> tuple[str, str]:
    """用 DeepSeek 为一篇文章生成 Pinterest Pin 标题和描述。"""
    if not DEEPSEEK_API_KEY:
        # 无 API Key 时退回简单文案
        title = article_title.strip("· ").strip()[:100]
        desc = (excerpt or title)[:400]
        return title, desc

    tag_str = ", ".join(tags) if tags else "luxury handbags"
    prompt = f"""You are a Pinterest marketing expert. Create a pin title and description for the following luxury bag article.

Article title: {article_title}
Summary: {excerpt}
Tags: {tag_str}

Requirements:
- Title: catchy, SEO-friendly, max 100 characters, include the brand name
- Description: engaging, 1-2 sentences, max 400 characters, include relevant keywords for Pinterest search
- Write in English
- Do NOT use hashtags in the title
- You may add 2-3 relevant hashtags at the end of the description

Output JSON: {{"title": "...", "description": "..."}}"""

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.8,
        "max_tokens": 300,
    }
    resp = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()["choices"][0]["message"]["content"]
    result = json.loads(data)
    return result["title"][:100], result["description"][:400]


# ---------- 文章扫描 ----------

def load_articles() -> list[dict]:
    """读取所有文章，返回 [{article_id, title, excerpt, url, images, tags}]。"""
    if not ARTICLES_DIR.exists():
        return []
    articles = []
    for f in sorted(ARTICLES_DIR.glob("*.json")):
        if f.name == "index.json":
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        slug = data.get("slug") or data.get("entry_id") or f.stem
        images = []
        # 封面图
        cover = data.get("cover_image") or data.get("source_cover")
        if cover:
            images.append(cover)
        # 正文图片
        for block in data.get("blocks", []):
            if block.get("type") == "image":
                url = block.get("full_url") or block.get("url")
                if url and url not in images:
                    images.append(url)
        if not images:
            continue
        articles.append({
            "article_id": slug,
            "title": data.get("title", "").strip("· ").strip(),
            "excerpt": data.get("excerpt", ""),
            "tags": data.get("tags", []),
            "url": BLOG_BASE_URL,
            "images": images,
        })
    return articles


# ---------- Google Sheets ----------

def get_sheet():
    """连接 Google Sheet，返回 worksheet。"""
    if not gspread:
        raise RuntimeError("gspread 未安装，请 pip install gspread google-auth")
    gc = gspread.service_account(filename=GOOGLE_SA_FILE)
    return gc.open_by_key(GOOGLE_SHEET_ID).sheet1


def get_synced_article_ids(ws) -> set:
    """读取已有数据中的 article_id 列，返回已同步的集合。"""
    try:
        col_values = ws.col_values(7)  # article_id 是第 7 列 (G)
        return set(col_values[1:])  # 跳过表头
    except Exception:
        return set()


def append_rows(ws, rows: list[list]):
    """批量追加行到 Sheet。"""
    if not rows:
        return
    ws.append_rows(rows, value_input_option="USER_ENTERED")


# ---------- 发 Pin ----------

def publish_pins(client: PinterestCookieClient, ws, max_pins: int):
    """从 Sheet 读取 status 为空的行，逐条发布。"""
    all_rows = ws.get_all_records()
    to_publish = [r for r in all_rows if str(r.get("status", "")).strip().lower() not in ("done", "published")]

    if not to_publish:
        print("没有待发布的 Pin")
        return 0, 0

    print(f"待发布: {len(to_publish)} 条 (本次最多发 {max_pins} 条)")
    success, failed = 0, 0
    # 找到 status 列号
    headers = ws.row_values(1)
    status_col = headers.index("status") + 1 if "status" in headers else 6

    count = 0
    for row in to_publish:
        if count >= max_pins:
            print(f"已达本次上限 {max_pins} 条，停止")
            break

        board_id = str(row.get("board_id", "")).strip()
        image_url = str(row.get("image_url", "")).strip()
        title = str(row.get("title", "")).strip()
        description = str(row.get("description", "")).strip()
        link = str(row.get("link", "")).strip()

        if not board_id or not image_url:
            print(f"  跳过: 缺少 board_id 或 image_url")
            failed += 1
            continue

        # 找到实际行号
        row_num = all_rows.index(row) + 2  # +1 for header, +1 for 0-indexed

        try:
            print(f"  [{count+1}] 发布: {title[:50]}")
            result = client.create_pin(
                board_id=board_id, image_url=image_url,
                title=title, description=description, link=link,
            )
            print(f"    -> 成功! Pin ID: {result['id']}")
            ws.update_cell(row_num, status_col, "done")
            success += 1
        except Exception as e:
            print(f"    -> 失败: {e}")
            ws.update_cell(row_num, status_col, f"error: {str(e)[:100]}")
            failed += 1

        count += 1
        # 随机延迟
        if count < max_pins and count < len(to_publish):
            delay = random.uniform(30, 60)
            print(f"    等待 {delay:.0f} 秒...")
            time.sleep(delay)

    return success, failed


# ---------- 主流程 ----------

def run_sync(dry_run: bool = False):
    """扫描文章 → DeepSeek 生成文案 → 写入 Google Sheets。"""
    print("=" * 60)
    print("步骤 1: 扫描博客文章")
    print("=" * 60)
    articles = load_articles()
    print(f"共找到 {len(articles)} 篇文章\n")

    print("=" * 60)
    print("步骤 2: 连接 Google Sheets")
    print("=" * 60)
    ws = get_sheet()

    # 确保表头正确
    existing_headers = ws.row_values(1)
    if existing_headers != SHEET_HEADERS:
        ws.update([SHEET_HEADERS])
        print(f"已设置表头: {SHEET_HEADERS}")

    synced = get_synced_article_ids(ws)
    print(f"已同步文章数: {len(synced)}\n")

    print("=" * 60)
    print("步骤 3: 生成 Pin 文案并同步")
    print("=" * 60)
    new_rows = []
    for article in articles:
        if article["article_id"] in synced:
            continue

        print(f"\n处理: {article['title'][:60]}")
        print(f"  图片数: {len(article['images'])}")
        print(f"  链接: {article['url']}")

        # DeepSeek 生成文案
        try:
            pin_title, pin_desc = deepseek_generate_pin(
                article["title"], article["excerpt"], article["tags"]
            )
            print(f"  标题: {pin_title}")
            print(f"  描述: {pin_desc[:80]}...")
        except Exception as e:
            print(f"  DeepSeek 失败 ({e}), 使用默认文案")
            pin_title = article["title"][:100]
            pin_desc = article["excerpt"][:400]

        # 为文章的每张图创建一行（最多 5 张）
        for img_url in article["images"][:5]:
            board_id = random.choice(BOARD_IDS) if BOARD_IDS else ""
            new_rows.append([
                board_id,          # board_id
                img_url,           # image_url
                pin_title,         # title
                pin_desc,          # description
                article["url"],    # link
                "",                # status (待发布)
                article["article_id"],  # article_id
                article["title"][:50],  # source (原标题，方便排查)
            ])

        # DeepSeek 限速
        time.sleep(1)

    if new_rows:
        print(f"\n写入 {len(new_rows)} 行到 Google Sheets...")
        append_rows(ws, new_rows)
        print("同步完成!")
    else:
        print("\n没有新文章需要同步")

    return len(new_rows)


def run_publish(dry_run: bool = False):
    """从 Google Sheets 读取并发布 Pin。"""
    print("\n" + "=" * 60)
    print("步骤 4: 发布 Pin")
    print("=" * 60)

    if not PINTEREST_SESS:
        print("警告: 未配置 PINTEREST_SESS，跳过发布")
        return 0, 0

    if dry_run:
        print("[dry-run] 跳过实际发布")
        return 0, 0

    client = PinterestCookieClient(PINTEREST_SESS, PINTEREST_PROXY)
    ws = get_sheet()
    return publish_pins(client, ws, MAX_PINS_PER_RUN)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="博客 → Pin 自动同步发布")
    parser.add_argument("--dry-run", action="store_true", help="只生成文案和同步 Sheets，不发 Pin")
    parser.add_argument("--sheets-only", action="store_true", help="只同步 Google Sheets")
    parser.add_argument("--publish-only", action="store_true", help="只发 Pin（从 Sheets 读取）")
    args = parser.parse_args()

    if not args.publish_only:
        run_sync(dry_run=args.dry_run)

    if not args.sheets_only:
        run_publish(dry_run=args.dry_run)

    print("\n完成!")


if __name__ == "__main__":
    main()
