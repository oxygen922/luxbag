"""配置加载：优先环境变量（.env），所有敏感信息不入库。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

# scraper 目录下的 .env
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


@dataclass(frozen=True)
class Config:
    # ---- 源站 ----
    sources: tuple = ("today", "feature")
    today_url: str = "https://bag.idai.ly/today"
    feature_url: str = "https://bag.idai.ly/feature"
    detail_base: str = "https://ibag.ly/entries/"   # 详情页规范链接
    max_pages: int = 1                               # 每个源每次最多翻几页
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
    request_timeout: int = 30

    # ---- 博客 / 流量归属 ----
    blog_base_url: str = "https://kynbag.blog"       # Pinterest Pin 的落地链接前缀

    # ---- 存储：Cloudflare R2（S3 兼容）----
    r2_enabled: bool = False
    r2_endpoint: str = ""        # https://<account_id>.r2.cloudflarestorage.com
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "kynbag"
    r2_public_base: str = ""     # 绑定到桶的自定义域名，如 https://cdn.kynbag.blog
    r2_region: str = "auto"

    # ---- DeepSeek 改写 ----
    deepseek_enabled: bool = False
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # ---- Pinterest 官方 API v5 ----
    pinterest_enabled: bool = False
    pinterest_app_id: str = ""
    pinterest_app_secret: str = ""
    pinterest_access_token: str = ""
    pinterest_refresh_token: str = ""
    pinterest_board_id: str = ""
    pinterest_api_base: str = "https://api.pinterest.com/v5"

    # ---- 运行参数 ----
    rewrite: bool = True          # 是否调用 DeepSeek 改写
    publish_pinterest: bool = True
    publish_all_images: bool = True   # 详情页每张图都发 Pin
    state_db: str = ""            # SQLite 路径（运行时填充）
    content_dir: str = ""         # 文章 JSON 输出目录（运行时填充）
    cache_dir: str = ""           # 原图下载缓存（运行时填充）


def load_config() -> Config:
    return Config(
        sources=tuple(s for s in _get("SOURCES", "today,feature").split(",") if s),
        max_pages=int(_get("MAX_PAGES", "1")),
        blog_base_url=_get("BLOG_BASE_URL", "https://kynbag.blog"),
        r2_enabled=_get("R2_ENABLED", "true").lower() == "true",
        r2_endpoint=_get("R2_ENDPOINT"),
        r2_access_key_id=_get("R2_ACCESS_KEY_ID"),
        r2_secret_access_key=_get("R2_SECRET_ACCESS_KEY"),
        r2_bucket=_get("R2_BUCKET", "kynbag"),
        r2_public_base=_get("R2_PUBLIC_BASE", "").rstrip("/"),
        r2_region=_get("R2_REGION", "auto"),
        deepseek_enabled=_get("DEEPSEEK_ENABLED", "true").lower() == "true",
        deepseek_api_key=_get("DEEPSEEK_API_KEY"),
        deepseek_base_url=_get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=_get("DEEPSEEK_MODEL", "deepseek-chat"),
        pinterest_enabled=_get("PINTEREST_ENABLED", "true").lower() == "true",
        pinterest_app_id=_get("PINTEREST_APP_ID"),
        pinterest_app_secret=_get("PINTEREST_APP_SECRET"),
        pinterest_access_token=_get("PINTEREST_ACCESS_TOKEN"),
        pinterest_refresh_token=_get("PINTEREST_REFRESH_TOKEN"),
        pinterest_board_id=_get("PINTEREST_BOARD_ID"),
        rewrite=_get("REWRITE", "true").lower() == "true",
        publish_pinterest=_get("PUBLISH_PINTEREST", "true").lower() == "true",
        publish_all_images=_get("PUBLISH_ALL_IMAGES", "true").lower() == "true",
    )


def init_paths(cfg: Config) -> Config:
    """填充运行时相对路径（state_db / content_dir / cache_dir）。"""
    base = os.path.dirname(__file__)
    object.__setattr__(cfg, "state_db", os.path.join(base, "state.db"))
    object.__setattr__(cfg, "content_dir", os.path.join(base, "..", "blog", "content", "articles"))
    object.__setattr__(cfg, "cache_dir", os.path.join(base, "cache"))
    os.makedirs(cfg.content_dir, exist_ok=True)
    os.makedirs(cfg.cache_dir, exist_ok=True)
    return cfg
