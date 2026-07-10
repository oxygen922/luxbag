"""图片/文章存储。双后端：

- R2（生产）：上传到 Cloudflare R2 桶，返回公开 CDN URL（Pinterest/博客共用）。
- 本地（开发）：写到 blog/public/images，返回 /images/... 相对路径，博客本地即可访问。

通过 R2_ENABLED 切换，业务代码无需感知后端差异。
"""
from __future__ import annotations

import os
import threading

from config import Config


class Storage:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._client = None
        self._lock = threading.Lock()
        # 只有同时配置了 endpoint 才真正启用 R2，否则退回本地存储
        self.enabled = cfg.r2_enabled and bool(cfg.r2_endpoint)
        if self.enabled:
            self._init_r2()

    # ---------- 后端初始化 ----------
    def _init_r2(self):
        import boto3  # 延迟导入
        self._client = boto3.client(
            "s3",
            endpoint_url=self.cfg.r2_endpoint,
            aws_access_key_id=self.cfg.r2_access_key_id,
            aws_secret_access_key=self.cfg.r2_secret_access_key,
            region_name=self.cfg.r2_region,
        )

    # ---------- 对外接口 ----------
    def upload_image(self, key: str, data: bytes, content_type: str = "image/jpeg") -> str:
        """上传一张图片，返回公开可访问 URL。"""
        if self.enabled and self._client:
            return self._r2_put(key, data, content_type)
        return self._local_put(key, data)

    def upload_json(self, key: str, text: str) -> str:
        if self.enabled and self._client:
            return self._r2_put(key, text.encode("utf-8"), "application/json")
        # 本地文章 JSON 由 article_store 直接写 content_dir，这里不重复
        return ""

    # ---------- R2 ----------
    def _r2_put(self, key: str, data: bytes, content_type: str) -> str:
        with self._lock:
            self._client.put_object(
                Bucket=self.cfg.r2_bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        base = self.cfg.r2_public_base or f"{self.cfg.r2_endpoint}/{self.cfg.r2_bucket}"
        return f"{base.rstrip('/')}/{key}"

    # ---------- 本地 ----------
    def _local_put(self, key: str, data: bytes) -> str:
        # 本地模式：key 形如 images/{entry_id}/{hash}.jpg，落到 blog/public 下，
        # 由 Next.js 静态服务，返回干净的 /images/{entry_id}/{hash}.jpg
        local_root = os.path.join(os.path.dirname(__file__), "..", "blog", "public")
        local_root = os.path.abspath(local_root)
        path = os.path.join(local_root, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return "/" + key.replace(os.sep, "/")
