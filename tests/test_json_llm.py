from __future__ import annotations

import pytest

from content_factory.domain.exceptions import AgentOutputParsingError
from content_factory.utils.json_llm import parse_llm_json


def test_parses_plain_json() -> None:
    assert parse_llm_json('{"a": 1}', agent_name="editor") == {"a": 1}


def test_parses_code_fenced_json() -> None:
    content = '```json\n{"decision": "approved", "reasons": []}\n```'
    assert parse_llm_json(content, agent_name="editor") == {
        "decision": "approved",
        "reasons": [],
    }


def test_strips_reasoning_think_block() -> None:
    """qwen3.6 gibi modeller düşünme bloğunu `content` içinde bırakıyor."""
    content = '<think>\nÖnce şunu düşüneyim... {"sahte": true}\n</think>\n{"decision": "rejected"}'
    assert parse_llm_json(content, agent_name="editor") == {"decision": "rejected"}


def test_strips_unterminated_think_block() -> None:
    """max_tokens'a takılan reasoning modeli `</think>` kapanışını hiç göndermez."""
    with pytest.raises(AgentOutputParsingError):
        parse_llm_json("<think>Düşünüyorum, henüz bitmedi", agent_name="editor")


def test_salvages_json_surrounded_by_prose() -> None:
    content = (
        'İşte değerlendirme sonucu:\n{"decision": "approved", "reasons": []}\n'
        "Umarım yardımcı olur."
    )
    assert parse_llm_json(content, agent_name="editor") == {
        "decision": "approved",
        "reasons": [],
    }


def test_salvages_json_array() -> None:
    content = 'Konular:\n[{"title": "Zeytinyağı"}]'
    assert parse_llm_json(content, agent_name="topic_scout") == [{"title": "Zeytinyağı"}]


def test_braces_inside_strings_do_not_break_salvage() -> None:
    content = 'Sonuç: {"reason": "şu ifade kullanılmış: {mucize}", "ok": false}'
    assert parse_llm_json(content, agent_name="editor") == {
        "reason": "şu ifade kullanılmış: {mucize}",
        "ok": False,
    }


def test_raises_when_no_json_present() -> None:
    with pytest.raises(AgentOutputParsingError):
        parse_llm_json("hiç JSON yok burada", agent_name="editor")
