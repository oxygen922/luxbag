"""Pinterest 官方 API v5 客户端。

- OAuth 2.0：access_token 约 30 天过期，refresh_token 约 365 天。
  本模块在 401 时自动用 refresh_token 换新 access_token，并回写 .env。
- 发图：POST /v5/pins，media_source 用 image_url（必须是公开 HTTPS，这里用 R2 CDN）。
- Pin 的 link 指向自有博客文章页（kynbag.blog），把流量沉淀到自己站。

首次授权请用 oauth.py 辅助脚本获取 access_token / refresh_token。
"""
from __future__ import annotations

import base64
import os
import re
import time

import requests

from config import Config


class PinterestError(RuntimeError):
    pass


class Pinterest:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.base = cfg.pinterest_api_base
        self._tokens_path = os.path.join(os.path.dirname(__file__), ".env")

    @property
    def _auth_header(self) -> dict:
        return {"Authorization": f"Bearer {self.cfg.pinterest_access_token}"}

    # ---------- token 刷新 ----------
    def _refresh(self):
        if not (self.cfg.pinterest_refresh_token and self.cfg.pinterest_app_id
                and self.cfg.pinterest_app_secret):
            raise PinterestError("缺少 refresh_token / app_id / app_secret，无法刷新，请重新授权。")
        basic = base64.b64encode(
            f"{self.cfg.pinterest_app_id}:{self.cfg.pinterest_app_secret}".encode()
        ).decode()
        r = requests.post(
            f"{self.base}/oauth/token",
            headers={"Authorization": f"Basic {basic}",
                     "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "refresh_token",
                  "refresh_token": self.cfg.pinterest_refresh_token},
            timeout=30,
        )
        if r.status_code != 200:
            raise PinterestError(f"刷新 token 失败: {r.status_code} {r.text}")
        data = r.json()
        # 更新内存配置（Config 是 frozen dataclass，用 object.__setattr__）
        object.__setattr__(self.cfg, "pinterest_access_token", data["access_token"])
        if data.get("refresh_token"):
            object.__setattr__(self.cfg, "pinterest_refresh_token", data["refresh_token"])
        self._persist_tokens(data["access_token"], data.get("refresh_token"))

    def _persist_tokens(self, access_token: str, refresh_token: str | None):
        """把新 token 回写 .env，保证后续运行可用。"""
        if not os.path.exists(self._tokens_path):
            return
        with open(self._tokens_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        out = []
        seen = set()
        for line in lines:
            if line.startswith("PINTEREST_ACCESS_TOKEN="):
                out.append(f"PINTEREST_ACCESS_TOKEN={access_token}\n"); seen.add("at")
            elif refresh_token and line.startswith("PINTEREST_REFRESH_TOKEN="):
                out.append(f"PINTEREST_REFRESH_TOKEN={refresh_token}\n"); seen.add("rt")
            else:
                out.append(line)
        if "at" not in seen:
            out.append(f"PINTEREST_ACCESS_TOKEN={access_token}\n")
        if refresh_token and "rt" not in seen:
            out.append(f"PINTEREST_REFRESH_TOKEN={refresh_token}\n")
        with open(self._tokens_path, "w", encoding="utf-8") as f:
            f.writelines(out)

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.base}{path}"
        kwargs.setdefault("headers", {}).update(self._auth_header)
        r = requests.request(method, url, timeout=60, **kwargs)
        if r.status_code == 401:
            self._refresh()
            kwargs["headers"].update(self._auth_header)
            r = requests.request(method, url, timeout=60, **kwargs)
        if r.status_code >= 400:
            raise PinterestError(f"{method} {path} 失败: {r.status_code} {r.text}")
        if r.status_code == 204 or not r.text:
            return {}
        return r.json()

    # ---------- 业务 ----------
    def create_pin(self, *, board_id: str, title: str, description: str,
                   link: str, image_url: str, alt_text: str = "") -> str:
        """创建图钉，返回 pin_id。image_url 必须公开 HTTPS。"""
        body = {
            "board_id": board_id,
            "title": title[:100],
            "description": description[:800],
            "link": link,
            "media_source": {"source_type": "image_url", "url": image_url},
            "alt_text": alt_text[:500],
        }
        data = self._request("POST", "/pins", json=body)
        return data.get("id", "")

    def list_boards(self) -> list[dict]:
        out, bookmark = [], None
        for _ in range(5):
            params = {"page_size": 50}
            if bookmark:
                params["bookmark"] = bookmark
            data = self._request("GET", "/boards", params=params)
            out.extend(data.get("items", []))
            bookmark = data.get("bookmark")
            if not bookmark:
                break
        return out


# ---------- 首次 OAuth 辅助 ----------
SCOPES = "user_accounts:read,pins:read,pins:write,boards:read,boards:write"


def authorize_url(cfg: Config, redirect_uri: str) -> str:
    return (
        "https://www.pinterest.com/oauth/?response_type=code"
        f"&client_id={cfg.pinterest_app_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={requests.utils.quote(SCOPES)}"
    )


def exchange_code(cfg: Config, code: str, redirect_uri: str) -> dict:
    """用授权码换取 access_token / refresh_token。"""
    basic = base64.b64encode(
        f"{cfg.pinterest_app_id}:{cfg.pinterest_app_secret}".encode()
    ).decode()
    r = requests.post(
        f"{cfg.pinterest_api_base}/oauth/token",
        headers={"Authorization": f"Basic {basic}",
                 "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "authorization_code",
              "code": code, "redirect_uri": redirect_uri},
        timeout=30,
    )
    if r.status_code != 200:
        raise PinterestError(f"换取 token 失败: {r.status_code} {r.text}")
    return r.json()
