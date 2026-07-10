"""HTTP 抓取：带 UA、超时、重试，统一升级到 HTTPS。"""
from __future__ import annotations

import time
import requests

from config import Config


def _https(url: str) -> str:
    """源站图片多为 http，统一升 https（Pinterest/CDN 要求）。"""
    if url.startswith("http://"):
        return "https://" + url[len("http://"):]
    return url


class Fetcher:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": cfg.user_agent})

    def get_text(self, url: str, retries: int = 3) -> str:
        url = _https(url)
        last_err: Exception | None = None
        for i in range(retries):
            try:
                r = self.session.get(url, timeout=self.cfg.request_timeout)
                r.raise_for_status()
                return r.text
            except Exception as e:  # noqa: BLE001
                last_err = e
                time.sleep(1.5 * (i + 1))
        raise RuntimeError(f"抓取失败 {url}: {last_err}")

    def get_bytes(self, url: str, retries: int = 3) -> bytes:
        url = _https(url)
        last_err: Exception | None = None
        for i in range(retries):
            try:
                r = self.session.get(url, timeout=self.cfg.request_timeout)
                r.raise_for_status()
                return r.content
            except Exception as e:  # noqa: BLE001
                last_err = e
                time.sleep(1.5 * (i + 1))
        raise RuntimeError(f"下载图片失败 {url}: {last_err}")
