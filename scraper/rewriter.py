"""DeepSeek 中→英改写（面向欧美受众）。

把中文箱包资讯翻译并改写为地道英文时尚博客文案，只处理【文本类区块】
（标题/段落/价格说明），保留 **加粗** 标记与排版结构；
图片网格/小节顺序等结构原样不动——从而「排版不会错乱」。

DeepSeek API 与 OpenAI 兼容，这里直接用 requests 调用，避免额外依赖。
"""
from __future__ import annotations

import json
import re

import requests

from config import Config

SYSTEM_PROMPT = """You are a senior English-language fashion editor for a luxury handbag blog aimed at Western (US/EU) readers. You will receive text segments (JSON) originally written in Chinese. Translate and rewrite them into natural, engaging, native-sounding English.

Rules:
1. Preserve ALL factual information exactly: brand names, model names, materials, prices, dimensions, and any numbers must NOT be changed.
2. Write in your own words — fluent, idiomatic English with the polished tone of a Western fashion publication. Avoid literal or machine-like translation.
3. Keep **bold** markers (**word**) in the same positions with the same emphasis.
4. "heading" items are section titles — keep them short and punchy, and keep the surrounding "·" decorations (e.g. "· Section Name ·").
5. "caption" items are price/label lines. Translate the Chinese label to English convention:
   - 官价 / 官方售价  -> "Retail price"
   - 价格店询          -> "Price upon request"
   Keep the currency symbol and amount as-is (e.g. "官价¥34,500" -> "Retail price ¥34,500"; "官价12,400美元" -> "Retail price $12,400").
6. Keep brand names in their original form (Louis Vuitton, Hermès, PRADA, etc.).
7. Output MUST be JSON: {"items":[{"index":0,"text":"..."}, ...]}. The array length and order must exactly match the input.
8. Do not add or remove any segments. Do not output any explanation."""


class Rewriter:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.enabled = cfg.deepseek_enabled and bool(cfg.deepseek_api_key)
        self.url = f"{cfg.deepseek_base_url.rstrip('/')}/chat/completions"

    def _post(self, system: str, user_content: str, *, json_mode: bool = False,
              temperature: float = 0.7, max_tokens: int | None = None) -> str:
        payload = {
            "model": self.cfg.deepseek_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if max_tokens:
            payload["max_tokens"] = max_tokens
        headers = {"Authorization": f"Bearer {self.cfg.deepseek_api_key}",
                   "Content-Type": "application/json"}
        r = requests.post(self.url, headers=headers, json=payload, timeout=120)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    def rewrite_text_blocks(self, items: list[dict]) -> list[str]:
        """items: [{"index":i,"type":"paragraph|heading|caption","text":"..."}] -> 英文文本列表。"""
        if not items:
            return []
        if not self.enabled:
            return [it["text"] for it in items]
        content = self._post(SYSTEM_PROMPT, json.dumps({"items": items}, ensure_ascii=False),
                             json_mode=True, temperature=0.7)
        data = json.loads(content)
        out_map = {it["index"]: it["text"] for it in data.get("items", [])}
        # 按原顺序回填，缺失则退回原文
        return [out_map.get(it["index"], it["text"]) for it in items]

    def make_excerpt(self, first_paragraph: str, title: str, max_len: int = 200) -> str:
        """生成英文摘要（不调用 API 时取首段截断）。"""
        if not first_paragraph:
            return title
        if not self.enabled:
            return first_paragraph[:max_len]
        try:
            txt = self._post(
                "In one concise English sentence (max 25 words), summarize the following handbag "
                "article text for a Western audience. Output only the summary, no quotes.",
                first_paragraph, temperature=0.5, max_tokens=120,
            )
            return txt.strip("「」“”\"'")[:max_len]
        except Exception:  # noqa: BLE001
            return first_paragraph[:max_len]


def clean_bold(text: str) -> str:
    """规整 ** 加粗标记间多余空白。"""
    return re.sub(r"\*\*\s*", "**", re.sub(r"\s*\*\*", "**", text))
