"""LLM'den JSON yanıt istenen agent'ların (TopicScout, Research, Strategist, SEO,
Editor, ScopeGuard) ortak kullandığı ayrıştırma yardımcı fonksiyonu.

Modeller çoğunlukla JSON'u ```` ```json ... ``` ```` code fence içine sarar; bu
fonksiyon fence'i temizleyip ayrıştırır. Aynı mantığı her agent kendi içinde tekrar
yazmasın diye burada tek bir yerde tutulur.
"""

from __future__ import annotations

import json
from typing import Any

from content_factory.domain.exceptions import AgentOutputParsingError


def parse_llm_json(content: str, *, agent_name: str) -> Any:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AgentOutputParsingError(
            f"{agent_name}: LLM yanıtı JSON olarak ayrıştırılamadı: {exc}"
        ) from exc
