"""数据模型：列表条目、详情文章、内容区块。

文章以「区块(blocks)」序列存储，忠实保留原图文排版结构，
便于博客前端按区块渲染、便于 DeepSeek 仅改写文本类区块。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import date


@dataclass
class EntrySummary:
    """列表页解析出的条目摘要。"""
    entry_id: str          # 如 ed3t0bs
    title: str
    source: str            # today / feature
    source_url: str        # 详情页规范链接 https://ibag.ly/entries/{id}
    list_url: str          # 所在列表页来源
    cover_url: str         # 列表页封面（icity CDN）
    date_label: str        # 如 "Jul 9, 2026"
    likes: int = 0


@dataclass
class Block:
    """内容区块。type 决定博客如何渲染。"""
    type: str              # paragraph / heading / image / grid / caption
    # 通用字段（按 type 取用）
    text: Optional[str] = None        # paragraph/heading/caption 的文本（含简单 HTML）
    url: Optional[str] = None         # image 的展示图 URL（已转存到自有 CDN）
    full_url: Optional[str] = None    # image 的原图 URL（已转存到自有 CDN）
    alt: Optional[str] = None
    columns: int = 2                  # grid 列数
    items: list = field(default_factory=list)  # grid: [{url, full_url, price}]


@dataclass
class Article:
    """一篇完整的文章（详情页解析 + 转存 + 改写后）。"""
    entry_id: str
    slug: str
    source: str                       # today / feature
    source_url: str
    source_cover: str                 # 源站原始封面
    title: str                        # 改写后标题
    original_title: str
    excerpt: str                      # 摘要
    author: str
    date_iso: str                     # YYYY-MM-DD
    date_label: str
    cover_image: str                  # 自有 CDN 封面 URL
    tags: list = field(default_factory=list)
    blocks: list = field(default_factory=list)  # List[Block]（序列化为 dict）
    pinterest: dict = field(default_factory=lambda: {"published": False, "pins": []})
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        return d
