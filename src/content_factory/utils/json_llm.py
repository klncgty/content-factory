"""LLM'den JSON yanıt istenen agent'ların (TopicScout, Research, Strategist, SEO,
Editor, ScopeGuard) ortak kullandığı ayrıştırma yardımcı fonksiyonu.

Modeller JSON'u nadiren "temiz" döndürür: çoğu ```` ```json ... ``` ```` code fence
içine sarar, reasoning modelleri (qwen3, deepseek-r1 türevleri) yanıtın başına
`<think>...</think>` bloğu koyar, bazıları JSON'un önüne/arkasına bir cümle ekler.
Aynı temizleme mantığını her agent kendi içinde tekrar yazmasın diye burada tek bir
yerde tutulur.
"""

from __future__ import annotations

import json
import re
from typing import Any

from content_factory.domain.exceptions import AgentOutputParsingError

_THINK_BLOCK = re.compile(r"<think>.*?(?:</think>|$)", re.DOTALL | re.IGNORECASE)
"""Reasoning modellerinin içeriğe gömdüğü düşünme bloğu. (OpenRouter/Groq'ta bu blok
çoğunlukla ayrı bir `reasoning` alanına çıkar, ama qwen3.6 gibi modeller `content`
içinde bırakıyor — o durumda JSON'dan önce gelip ayrıştırmayı bozar.)

Kapanış etiketi opsiyoneldir: yanıt max_tokens'a takılıp düşünmenin ortasında kesildiğinde
`</think>` hiç gelmez; o hâlde blok metnin sonuna kadar sayılır ve geriye JSON kalmadığı
net biçimde görülür (yarım düşünme metnini JSON sanıp ayrıştırmaya çalışmayız)."""


def parse_llm_json(content: str, *, agent_name: str) -> Any:
    text = _THINK_BLOCK.sub("", content).strip()
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
        salvaged = _first_json_value(text)
        if salvaged is not None:
            return salvaged
        raise AgentOutputParsingError(
            f"{agent_name}: LLM yanıtı JSON olarak ayrıştırılamadı: {exc}"
        ) from exc


def _first_json_value(text: str) -> Any | None:
    """Metnin içindeki ilk dengeli JSON nesnesini/dizisini ayrıştırmayı dener.

    Model JSON'un önüne veya arkasına serbest metin eklediğinde ("İşte değerlendirme:
    {...}") tüm yanıtı çöpe atmak yerine JSON'u kurtarır. Dengeli parantez sayımı
    kullanılır; string içindeki parantezler ve kaçış karakterleri atlanır."""
    # Metinde önce hangisi geçiyorsa o denenir: `[{...}]` içeren bir yanıtta önce "{"
    # aranırsa dizinin ilk elemanı kurtarılıp dizinin kendisi kaybedilirdi.
    openers = (("{", "}"), ("[", "]"))
    candidates = [(text.find(o), o, c) for o, c in openers]
    for start, opener, closer in sorted(c for c in candidates if c[0] != -1):
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == opener:
                depth += 1
            elif char == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : index + 1])
                    except json.JSONDecodeError:
                        break
    return None
