"""文章输出：把 Article 写成 JSON 落到 content/articles，并维护索引。

content/articles/{entry_id}.json   单篇文章（区块结构）
content/index.json                 全站文章索引（博客列表页用）
"""
from __future__ import annotations

import json
import os

from models import Article


class ArticleStore:
    def __init__(self, content_dir: str):
        self.content_dir = content_dir
        os.makedirs(content_dir, exist_ok=True)

    def path_for(self, entry_id: str) -> str:
        return os.path.join(self.content_dir, f"{entry_id}.json")

    def write(self, article: Article):
        path = self.path_for(article.entry_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(article.to_dict(), f, ensure_ascii=False, indent=2)

    def read(self, entry_id: str) -> dict | None:
        path = self.path_for(entry_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def rebuild_index(self):
        items = []
        for name in sorted(os.listdir(self.content_dir)):
            if not name.endswith(".json") or name == "index.json":
                continue
            with open(os.path.join(self.content_dir, name), "r", encoding="utf-8") as f:
                a = json.load(f)
            items.append({
                "id": a["entry_id"],
                "slug": a["slug"],
                "title": a["title"],
                "date": a["date_iso"],
                "cover": a["cover_image"],
                "excerpt": a["excerpt"],
                "tags": a.get("tags", []),
                "source": a["source"],
            })
        # 按日期倒序
        items.sort(key=lambda x: x.get("date", ""), reverse=True)
        with open(os.path.join(self.content_dir, "index.json"), "w", encoding="utf-8") as f:
            json.dump({"articles": items}, f, ensure_ascii=False, indent=2)
        return len(items)
