"""采集→转存→改写→发布 主编排管线。

每个阶段可独立重入（断点续跑），由 DB 的阶段标志位驱动：
  discover → fetch_detail → transfer_images → rewrite → publish_pinterest → save_article
"""
from __future__ import annotations

import hashlib
import os
import re
import time
import traceback
from dataclasses import replace

from config import Config
from fetcher import Fetcher
from parser import parse_list_page, parse_detail_page, parse_pagination_last, _scrub_text as _scrub
from storage import Storage
from rewriter import Rewriter, clean_bold
from pinterest import Pinterest
from db import DB
from article_store import ArticleStore
from models import Article, Block

BRANDS = [
    "Louis Vuitton", "LV", "Hermès", "HERMÈS", "CHANEL", "CELINE", "Dior", "PRADA",
    "MIU MIU", "Miu Miu", "FENDI", "LOEWE", "BALENCIAGA", "Balenciaga", "GUCCI",
    "BVLGARI", "BOTTEGA VENETA", "SAINT LAURENT", "Goyard", "VALENTINO", "GIVENCHY",
]


def _slugify(entry_id: str) -> str:
    return entry_id


def _guess_tags(title: str) -> list[str]:
    found = []
    for b in BRANDS:
        if re.search(re.escape(b), title, re.I):
            if b not in found:
                found.append(b)
    # 归并大小写变体
    norm = {b.lower(): b for b in found}
    return list(norm.values())[:5]


def _url_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:16]


class Pipeline:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.fetcher = Fetcher(cfg)
        self.storage = Storage(cfg)
        self.rewriter = Rewriter(cfg)
        self.db = DB(cfg.state_db)
        self.store = ArticleStore(cfg.content_dir)

    # ---------------- 阶段 1：发现 ----------------
    def discover(self):
        total = 0
        for source in self.cfg.sources:
            base_url = self.cfg.feature_url if source == "feature" else self.cfg.today_url
            for page in range(1, self.cfg.max_pages + 1):
                list_url = base_url if page == 1 else f"{base_url}?page={page}"
                html = self.fetcher.get_text(list_url)
                entries = parse_list_page(html, source, list_url, self.cfg.detail_base)
                for e in entries:
                    self.db.upsert_discovered(e)
                total += len(entries)
                # 不足一页或到末页则停
                if page >= self.cfg.max_pages:
                    break
                if len(entries) < 12:
                    break
                time.sleep(1)
        print(f"[discover] 新增/更新 {total} 条索引")
        return total

    # ---------------- 阶段 2：抓详情 ----------------
    def fetch_details(self, limit: int = 20):
        rows = self.db.pending_for_stage("fetched", limit)
        print(f"[fetch_details] 待抓 {len(rows)} 篇")
        for row in rows:
            try:
                html = self.fetcher.get_text(row["source_url"])
                parsed = parse_detail_page(html)
                # 暂存解析结果到 article JSON（图片仍是源 URL）
                art = Article(
                    entry_id=row["entry_id"], slug=_slugify(row["entry_id"]),
                    source=row["source"], source_url=row["source_url"],
                    source_cover="", title=parsed["title"],
                    original_title=parsed["original_title"], excerpt="",
                    author=parsed["author"], date_iso=parsed["date_iso"],
                    date_label=parsed["date_label"], cover_image=parsed["cover_source"],
                    tags=_guess_tags(parsed["title"]), blocks=parsed["blocks"],
                )
                self.store.write(art)
                self.db.set_status(row["entry_id"], "fetched", detail_fetched=1)
                print(f"  ✓ {row['entry_id']} {parsed['title'][:30]}")
            except Exception as e:  # noqa: BLE001
                self.db.set_status(row["entry_id"], "fetched", error=str(e)[:200])
                print(f"  ✗ {row['entry_id']} {e}")

    # ---------------- 阶段 3：转存图片 ----------------
    def transfer_images(self, limit: int = 20):
        rows = self.db.pending_for_stage("transferred", limit)
        print(f"[transfer_images] 待转存 {len(rows)} 篇")
        for row in rows:
            try:
                data = self.store.read(row["entry_id"])
                if not data:
                    self.db.set_status(row["entry_id"], "fetched", detail_fetched=0)
                    continue
                url_map = self._collect_and_upload(data)
                # 替换封面与区块里的源 URL
                data["cover_image"] = url_map.get(data.get("cover_image", ""), data.get("cover_image", ""))
                for b in data["blocks"]:
                    if b["type"] == "image":
                        b["url"] = url_map.get(b.get("url", ""), b.get("url", ""))
                        b["full_url"] = url_map.get(b.get("full_url", ""), b.get("full_url", ""))
                    elif b["type"] == "grid":
                        for it in b["items"]:
                            it["url"] = url_map.get(it.get("url", ""), it.get("url", ""))
                            it["full_url"] = url_map.get(it.get("full_url", ""), it.get("full_url", ""))
                self.store.write(Article(**{**data, "blocks": data["blocks"]}))
                self.db.set_status(row["entry_id"], "transferred",
                                   images_transferred=1, cover_cdn=data["cover_image"])
                print(f"  ✓ {row['entry_id']} 转存 {len(url_map)} 图")
            except Exception as e:  # noqa: BLE001
                self.db.set_status(row["entry_id"], "transferred", error=str(e)[:200])
                print(f"  ✗ {row['entry_id']} {e}")

    def _collect_and_upload(self, data: dict) -> dict:
        urls = set()
        if data.get("cover_image"):
            urls.add(data["cover_image"])
        for b in data["blocks"]:
            if b["type"] == "image":
                if b.get("url"):
                    urls.add(b["url"])
                if b.get("full_url"):
                    urls.add(b["full_url"])
            elif b["type"] == "grid":
                for it in b["items"]:
                    if it.get("url"):
                        urls.add(it["url"])
                    if it.get("full_url"):
                        urls.add(it["full_url"])
        url_map: dict[str, str] = {}
        for u in urls:
            if not u:
                continue
            # 幂等保护：已转存的本地/CDN 相对 URL 不再重复下载
            if not u.startswith("http"):
                url_map[u] = u
                continue
            try:
                raw = self._fetch_cached(u)
                ext = "jpg"
                key = f"images/{data['entry_id']}/{_url_hash(u)}.{ext}"
                cdn = self.storage.upload_image(key, raw, "image/jpeg")
                url_map[u] = cdn
            except Exception as e:  # noqa: BLE001
                print(f"    ! 图片失败 {u}: {e}")
                url_map[u] = u  # 退回源 URL
        return url_map

    def _fetch_cached(self, url: str) -> bytes:
        h = _url_hash(url)
        cache_path = os.path.join(self.cfg.cache_dir, h)
        if os.path.exists(cache_path):
            with open(cache_path, "rb") as f:
                return f.read()
        data = self.fetcher.get_bytes(url)
        with open(cache_path, "wb") as f:
            f.write(data)
        return data

    # ---------------- 阶段 4：AI 改写 ----------------
    def rewrite(self, limit: int = 20):
        rows = self.db.pending_for_stage("rewritten", limit)
        print(f"[rewrite] 待改写 {len(rows)} 篇 (enabled={self.rewriter.enabled})")
        for row in rows:
            try:
                data = self.store.read(row["entry_id"])
                if not data:
                    continue
                text_items = []
                for i, b in enumerate(data["blocks"]):
                    if b["type"] in ("paragraph", "heading", "caption"):
                        text_items.append({"index": i, "type": b["type"], "text": b.get("text", "")})
                if text_items:
                    new_texts = self.rewriter.rewrite_text_blocks(text_items)
                    for item, new in zip(text_items, new_texts):
                        data["blocks"][item["index"]]["text"] = _scrub(clean_bold(new))
                # 标题改写
                data["title"] = _scrub(clean_bold(
                    self.rewriter.rewrite_text_blocks([{"index": 0, "type": "heading", "text": data["title"]}])[0]
                ))
                # 摘要
                first_para = next((b["text"] for b in data["blocks"] if b["type"] == "paragraph"), "")
                data["excerpt"] = self.rewriter.make_excerpt(first_para, data["title"])
                self.store.write(Article(**data))
                self.db.set_status(row["entry_id"], "rewritten", rewritten=1)
                print(f"  ✓ {row['entry_id']} 已改写")
            except Exception as e:  # noqa: BLE001
                self.db.set_status(row["entry_id"], "rewritten", error=str(e)[:200])
                print(f"  ✗ {row['entry_id']} {e}")

    # ---------------- 阶段 5：发布 Pinterest ----------------
    def publish(self, limit: int = 10):
        if not (self.cfg.pinterest_enabled and self.cfg.publish_pinterest
                and self.cfg.pinterest_access_token and self.cfg.pinterest_board_id):
            print("[publish] Pinterest 未启用或缺少配置，跳过（文章仍会写入博客）。")
            return
        if not self.storage.enabled:
            print("[publish] 警告：未启用 R2，本地图片 URL 非公开，Pinterest 跳过。")
            return
        pin = Pinterest(self.cfg)
        rows = self.db.pending_for_stage("published", limit)
        print(f"[publish] 待发布 {len(rows)} 篇")
        for row in rows:
            try:
                data = self.store.read(row["entry_id"])
                if not data:
                    continue
                link = f"{self.cfg.blog_base_url.rstrip('/')}/articles/{data['slug']}"
                desc_base = f"{data.get('excerpt','')} {data.get('author','')}".strip()
                # 收集所有可发图（封面 + 区块图 + 网格图），去重
                images: list[tuple[str, str]] = []  # (image_url, alt/title)
                if data.get("cover_image"):
                    images.append((data["cover_image"], data["title"]))
                for b in data["blocks"]:
                    if b["type"] == "image":
                        img = b.get("full_url") or b.get("url")
                        if img:
                            images.append((img, data["title"]))
                    elif b["type"] == "grid" and self.cfg.publish_all_images:
                        for it in b["items"]:
                            img = it.get("full_url") or it.get("url")
                            if img:
                                images.append((img, data["title"]))
                seen = set()
                count = 0
                for img_url, alt in images:
                    if img_url in seen or not img_url.startswith("https://"):
                        continue
                    seen.add(img_url)
                    pin_id = pin.create_pin(
                        board_id=self.cfg.pinterest_board_id,
                        title=data["title"], description=desc_base,
                        link=link, image_url=img_url, alt_text=alt,
                    )
                    self.db.add_pin(row["entry_id"], pin_id, img_url)
                    count += 1
                    time.sleep(3)  # 礼貌限速
                self.db.set_status(row["entry_id"], "published")
                print(f"  ✓ {row['entry_id']} 发布 {count} 个 Pin")
            except Exception as e:  # noqa: BLE001
                self.db.set_status(row["entry_id"], "published", error=str(e)[:200])
                print(f"  ✗ {row['entry_id']} {e}")

    # ---------------- 一键全流程 ----------------
    def run_all(self):
        self.discover()
        self.fetch_details()
        self.transfer_images()
        if self.cfg.rewrite:
            self.rewrite()
        if self.cfg.publish_pinterest:
            self.publish()
        n = self.store.rebuild_index()
        print(f"[done] 博客索引已重建，共 {n} 篇文章。")
