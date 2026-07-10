"""命令行入口。

常用：
  python main.py run            # 一键全流程
  python main.py discover       # 只扫描列表页
  python main.py fetch          # 抓详情
  python main.py transfer       # 转存图片到 R2/本地
  python main.py rewrite        # DeepSeek 改写
  python main.py publish        # 发 Pinterest
  python main.py index          # 重建博客索引
  python main.py boards         # 列出 Pinterest 画板（确认 board_id）
  python main.py oauth --redirect-uri <url> [--code <code>]
"""
from __future__ import annotations

import argparse
import sys

from config import load_config, init_paths
from pipeline import Pipeline
from pinterest import Pinterest, authorize_url, exchange_code


def main():
    cfg = init_paths(load_config())
    p = Pipeline(cfg)
    parser = argparse.ArgumentParser(description="iBag → 自有博客 + Pinterest 自动化")
    parser.add_argument("cmd", choices=[
        "run", "discover", "fetch", "transfer", "rewrite", "publish", "index", "boards", "oauth"])
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--redirect-uri", default="https://kynbag.blog/callback")
    parser.add_argument("--code", default=None)
    args = parser.parse_args()

    if args.cmd == "run":
        p.run_all()
    elif args.cmd == "discover":
        p.discover(); p.store.rebuild_index()
    elif args.cmd == "fetch":
        p.fetch_details(args.limit); p.store.rebuild_index()
    elif args.cmd == "transfer":
        p.transfer_images(args.limit); p.store.rebuild_index()
    elif args.cmd == "rewrite":
        p.rewrite(args.limit); p.store.rebuild_index()
    elif args.cmd == "publish":
        p.publish(args.limit); p.store.rebuild_index()
    elif args.cmd == "index":
        n = p.store.rebuild_index(); print(f"索引重建完成，{n} 篇")
    elif args.cmd == "boards":
        boards = Pinterest(cfg).list_boards()
        for b in boards:
            print(f"{b.get('id')}  {b.get('name')}  ({b.get('pin_count')} pins)")
    elif args.cmd == "oauth":
        if args.code:
            data = exchange_code(cfg, args.code, args.redirect_uri)
            print("access_token:", data.get("access_token"))
            print("refresh_token:", data.get("refresh_token"))
            print("scope:", data.get("scope"))
            print("请把以上 token 填入 scraper/.env")
        else:
            print("请在浏览器打开下面链接完成授权，授权后会跳转到 redirect_uri 并带上 ?code=...：\n")
            print(authorize_url(cfg, args.redirect_uri))
            print("\n拿到 code 后运行：python main.py oauth --redirect-uri <url> --code <CODE>")


if __name__ == "__main__":
    main()
