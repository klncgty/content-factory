from __future__ import annotations

import dataclasses
import json

import pytest

from content_factory.agents.base import AgentContext
from content_factory.agents.editor import EditorAgent
from content_factory.domain.exceptions import AgentValidationError
from content_factory.domain.models import (
    Article,
    BodyLink,
    EditorInput,
    LinkPlan,
    QADecision,
    ResearchNotes,
    ScopeDecision,
    ScopeRejectionRecord,
    Topic,
)
from content_factory.settings.schemas import GroundingConfig

from ..support.stub_llm import StubLLMProvider

_IN_SCOPE = json.dumps({"group_id": "olive_and_oil", "reason": "zeytinyağı hakkında"})
_OUT_OF_SCOPE = json.dumps({"group_id": "out_of_scope", "reason": "genel diyet tavsiyesi"})
_APPROVED = json.dumps({"decision": "approved", "reasons": []})

_QUOTED_SENTENCE = "Soğuk sıkım yöntemi yağın besin değerini korur"
"""Editörün gerekçesine çıpa olarak koyduğu, makalede BİREBİR geçen alıntı."""

_REJECTED = json.dumps({
    "decision": "rejected",
    "reasons": [
        {
            "alinti": _QUOTED_SENTENCE,
            "sorun": "Aynı fikir bir önceki bölümde anlatılmış.",
            "duzeltme": "Bu paragrafı çıkar.",
        }
    ],
})


def _body(word_count: int = 900) -> str:
    return " ".join(["zeytinyağı"] * word_count)


def _article_with(sentence: str, *, word_count: int = 900) -> Article:
    """Verilen cümleyi gerçekten içeren bir makale — alıntı doğrulamasının geçebilmesi
    için gerekli."""
    return _article(body_markdown=f"{sentence}. {_body(word_count)}")


def _article(**overrides: object) -> Article:
    defaults: dict[str, object] = {
        "brand": "oleart",
        "slug": "zeytinyagi-donar-mi",
        "title": "Zeytinyağı Donar mı?",
        "body_markdown": _body(),
    }
    return Article(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_llm_quality_review_receives_research_key_facts(agent_context: AgentContext) -> None:
    stub = StubLLMProvider(responses=[_IN_SCOPE, _APPROVED])
    agent_context.llm = stub
    agent = EditorAgent(agent_context)
    research = ResearchNotes(
        topic=Topic(brand="oleart", title="Zeytinyağı Donar mı?"),
        key_facts=["Zeytinyağı 4°C altında donmaya başlar."],
    )

    agent(EditorInput(article=_article(), research=research))

    quality_review_prompt = stub.requests[1].messages[0].content
    assert "Zeytinyağı 4°C altında donmaya başlar." in quality_review_prompt


def test_approves_clean_article(agent_context: AgentContext) -> None:
    # 1. yanıt ScopeGuard.post_check'e, 2. yanıt kalite incelemesine gider.
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE, _APPROVED])
    agent = EditorAgent(agent_context)

    report = agent(EditorInput(article=_article()))

    assert report.decision is QADecision.APPROVED
    assert report.scope_decision is ScopeDecision.IN_SCOPE
    assert report.reasons == []


def test_rejects_on_forbidden_word(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE])
    agent = EditorAgent(agent_context)

    article = _article(body_markdown=f"{_body()} Bu bir mucize üründür.")
    report = agent(EditorInput(article=article))

    assert report.decision is QADecision.REJECTED
    assert any("mucize" in reason for reason in report.reasons)


def _with_grounding_enforced(context: AgentContext) -> AgentContext:
    """`engine.yaml: grounding.enforce` açıkken bir bağlam üretir (varsayılan kapalıdır)."""
    context.settings = dataclasses.replace(
        context.settings,
        engine=context.settings.engine.model_copy(
            update={"grounding": GroundingConfig(enforce=True)}
        ),
    )
    return context


def test_rejects_on_ungrounded_numeric_claim(agent_context: AgentContext) -> None:
    """`enforce` açıkken GroundingGuard katman 1'dedir: LLM kalite incelemesi (2. yanıt)
    hiç çalışmadan reddedilir — bkz. `guards/grounding_guard.py`."""
    agent_context = _with_grounding_enforced(agent_context)
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE])
    agent = EditorAgent(agent_context)

    article = _article(body_markdown=f"{_body()} İdeal saklama aralığı 14-18°C'dir.")
    report = agent(EditorInput(article=article))

    assert report.decision is QADecision.REJECTED
    assert any("14-18°C" in reason for reason in report.reasons)


def test_ungrounded_claim_only_warns_when_enforce_is_off(agent_context: AgentContext) -> None:
    """Varsayılan (uyarı) modda zeminsiz sayı bulguları karara KATILMAZ — guard'ın
    gerçek makalelerdeki isabeti yayın turunu riske atmadan ölçülebilsin diye."""
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE, _APPROVED])
    agent = EditorAgent(agent_context)

    article = _article(body_markdown=f"{_body()} İdeal saklama aralığı 14-18°C'dir.")
    report = agent(EditorInput(article=article))

    assert agent_context.settings.engine.grounding.enforce is False
    assert report.decision is QADecision.APPROVED
    assert report.reasons == []


def test_grounded_numeric_claim_does_not_block_approval(agent_context: AgentContext) -> None:
    """Knowledge'da geçen bir sayı (duman noktası 190-210°C) reddedilmemeli."""
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE, _APPROVED])
    agent = EditorAgent(agent_context)

    article = _article(body_markdown=f"{_body()} Duman noktası 190-210°C aralığındadır.")
    report = agent(EditorInput(article=article))

    assert report.decision is QADecision.APPROVED


def test_research_key_facts_ground_numeric_claims(agent_context: AgentContext) -> None:
    """Araştırma notlarındaki bir sayı, knowledge'da geçmese de iddiayı zeminler."""
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE, _APPROVED])
    agent = EditorAgent(agent_context)
    research = ResearchNotes(
        topic=Topic(brand="oleart", title="Sele Zeytini"),
        key_facts=["Sele zeytini salamurada yaklaşık 7 ay bekletilir."],
    )

    article = _article(body_markdown=f"{_body()} Sele zeytini 7 ay salamurada kalır.")
    report = agent(EditorInput(article=article, research=research))

    assert report.decision is QADecision.APPROVED


def test_rejects_on_forbidden_claim(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE])
    agent = EditorAgent(agent_context)

    article = _article(body_markdown=f"{_body()} Zeytinyağı hastalığı tedavi eder.")
    report = agent(EditorInput(article=article))

    assert report.decision is QADecision.REJECTED
    assert any("hastalığı tedavi eder" in reason for reason in report.reasons)


def test_rejects_when_too_short(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE])
    agent = EditorAgent(agent_context)

    report = agent(EditorInput(article=_article(body_markdown=_body(50))))

    assert report.decision is QADecision.REJECTED
    assert any("çok kısa" in reason for reason in report.reasons)


def test_rejects_when_too_long(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE])
    agent = EditorAgent(agent_context)

    report = agent(EditorInput(article=_article(body_markdown=_body(5000))))

    assert report.decision is QADecision.REJECTED
    assert any("çok uzun" in reason for reason in report.reasons)


def test_deterministic_failure_skips_expensive_quality_call(
    agent_context: AgentContext,
) -> None:
    """Makale zaten reddedilecekse pahalı kalite modeline çağrı yapılmamalı —
    yalnızca ScopeGuard'ın ucuz sınıflandırma çağrısı yapılır."""
    stub = StubLLMProvider(responses=[_IN_SCOPE, _APPROVED])
    agent_context.llm = stub
    agent = EditorAgent(agent_context)

    agent(EditorInput(article=_article(body_markdown=_body(50))))

    assert len(stub.requests) == 1


def test_scope_post_check_runs_even_when_deterministic_checks_fail(
    agent_context: AgentContext,
) -> None:
    """`QAReport.scope_decision` her zaman gerçek bir ölçümü yansıtmalı."""
    agent_context.llm = StubLLMProvider(responses=[_OUT_OF_SCOPE])
    agent = EditorAgent(agent_context)

    report = agent(EditorInput(article=_article(body_markdown=_body(50))))

    assert report.scope_decision is ScopeDecision.OUT_OF_SCOPE
    assert any("Kapsam dışı" in reason for reason in report.reasons)


def test_out_of_scope_is_logged_to_state_store(
    agent_context: AgentContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    logged: list[ScopeRejectionRecord] = []
    monkeypatch.setattr(agent_context.state, "log_scope_rejection", logged.append)
    agent_context.llm = StubLLMProvider(responses=[_OUT_OF_SCOPE])
    agent = EditorAgent(agent_context)

    agent(EditorInput(article=_article()))

    assert len(logged) == 1
    assert logged[0].stage == "editor"
    assert logged[0].reason == "genel diyet tavsiyesi"


def test_rejects_when_planned_link_missing_from_body(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE])
    agent = EditorAgent(agent_context)

    link_plan = LinkPlan(
        new_article_body_links=[BodyLink(anchor="erken hasat", target_slug="erken-hasat-nedir")]
    )
    report = agent(EditorInput(article=_article(), link_plan=link_plan))

    assert report.decision is QADecision.REJECTED
    assert any("Planlanan iç link" in reason for reason in report.reasons)


def test_accepts_applied_body_link(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE, _APPROVED])
    agent = EditorAgent(agent_context)

    body = f"{_body()} [erken hasat](/blog/erken-hasat-nedir/) hakkında."
    link_plan = LinkPlan(
        new_article_body_links=[BodyLink(anchor="erken hasat", target_slug="erken-hasat-nedir")]
    )
    report = agent(EditorInput(article=_article(body_markdown=body), link_plan=link_plan))

    assert report.decision is QADecision.APPROVED


def test_llm_rejection_reasons_are_propagated(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE, _REJECTED])
    agent = EditorAgent(agent_context)

    report = agent(EditorInput(article=_article_with(_QUOTED_SENTENCE)))

    assert report.decision is QADecision.REJECTED
    # Writer'a giden satır alıntıyı, sorunu ve düzeltmeyi birlikte taşır — Writer
    # prompt'u "yalnızca alıntının geçtiği yere dokun" diyor.
    assert report.reasons == [
        f"«{_QUOTED_SENTENCE}» — Aynı fikir bir önceki bölümde anlatılmış. "
        "Düzeltme: Bu paragrafı çıkar."
    ]


def test_rejection_whose_quote_is_not_in_the_article_is_discarded(
    agent_context: AgentContext,
) -> None:
    """06.08.2026 arızasının regresyon testi: editör metinde GEÇMEYEN ifadeleri gerekçe
    göstererek aynı makaleyi dört kez reddetti. Gösterilebilir tek bir ihlal yoksa geçit
    açılmalıdır — aksi hâlde Writer olmayan bir sorunu düzeltmeye çalışır."""
    hallucinated = json.dumps({
        "decision": "rejected",
        "reasons": [
            {
                "alinti": "smoke point",
                "sorun": "İngilizce sözcük kullanılmış.",
                "duzeltme": "Türkçesini yaz.",
            }
        ],
    })
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE, hallucinated])
    agent = EditorAgent(agent_context)

    report = agent(EditorInput(article=_article()))

    assert report.decision is QADecision.APPROVED
    assert report.reasons == []


def test_rejection_with_english_justification_is_discarded(
    agent_context: AgentContext,
) -> None:
    """Alıntı doğru olsa bile İngilizce yazılmış bir gerekçe karara katılmaz: Türkçe
    yazmayan bir model prompt'u tümden yok saymıştır ve o geri bildirim Writer'ı da
    dilden çıkarma riski taşır (06.08.2026'da son reddetme gerekçesi İngilizceydi)."""
    english_review = json.dumps({
        "decision": "rejected",
        "reasons": [
            {
                "alinti": _QUOTED_SENTENCE,
                "sorun": "The article contains phrases which are not allowed and the tone is off.",
                "duzeltme": "Rewrite this sentence.",
            }
        ],
    })
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE, english_review])
    agent = EditorAgent(agent_context)

    report = agent(EditorInput(article=_article_with(_QUOTED_SENTENCE)))

    assert report.decision is QADecision.APPROVED


def test_rejection_without_reasons_is_ignored(agent_context: AgentContext) -> None:
    """Gerekçesiz bir red, Writer'a hiçbir şey söylemez — retry döngüsü aynı taslağı
    tekrar üretirdi. Gerekçe gösteremeyen bir red, doğrulanamayan bir redle aynı şeydir."""
    agent_context.llm = StubLLMProvider(
        responses=[_IN_SCOPE, json.dumps({"decision": "rejected"})]
    )
    agent = EditorAgent(agent_context)

    report = agent(EditorInput(article=_article()))

    assert report.decision is QADecision.APPROVED
    assert report.reasons == []


def test_plain_string_reason_is_discarded(agent_context: AgentContext) -> None:
    """Model eski şemaya (düz string gerekçe) düşerse bulgu alıntısız kalır ve elenir.
    Sessizce kabul etmek, doğrulama katmanını baypas etmek olurdu."""
    agent_context.llm = StubLLMProvider(
        responses=[
            _IN_SCOPE,
            json.dumps({"decision": "rejected", "reasons": ["Metin genel olarak zayıf."]}),
        ]
    )
    agent = EditorAgent(agent_context)

    report = agent(EditorInput(article=_article()))

    assert report.decision is QADecision.APPROVED


def test_malformed_review_is_repaired_on_second_attempt(agent_context: AgentContext) -> None:
    """Model biçimden saparsa (JSON yerine düz metin) inceleme bir kez daha, biçim şartı
    hatırlatılarak istenir — biçim sapması makale hakkında bir yargı değildir."""
    stub = StubLLMProvider(
        responses=[_IN_SCOPE, "Makale genel olarak iyi görünüyor, onaylıyorum.", _APPROVED]
    )
    agent_context.llm = stub
    agent = EditorAgent(agent_context)

    report = agent(EditorInput(article=_article()))

    assert report.decision is QADecision.APPROVED
    assert len(stub.requests) == 3  # scope + bozuk inceleme + onarım turu
    assert "yalnızca tek bir json nesnesi" in stub.requests[2].messages[0].content.lower()


def test_unparseable_review_rejects_instead_of_crashing(agent_context: AgentContext) -> None:
    """Onarım turu da başarısızsa geçit KAPALI kalır: makale reddedilir ama run çökmez.

    Geçmişte bu durum `AgentOutputParsingError` olarak yükselip tüm yayın turunu exit 1
    ile öldürüyordu (03.08.2026). Kritik olan, incelemesi yapılamamış bir makalenin asla
    ONAYLANMAMASIDIR."""
    stub = StubLLMProvider(responses=[_IN_SCOPE, "JSON değil", "yine JSON değil"])
    agent_context.llm = stub
    agent = EditorAgent(agent_context)

    report = agent(EditorInput(article=_article()))

    assert report.decision is QADecision.REJECTED
    assert any("okunamadı" in reason for reason in report.reasons)
    assert report.scope_decision is ScopeDecision.IN_SCOPE  # gerçek ölçüm korunur


def test_invalid_decision_value_also_fails_closed(agent_context: AgentContext) -> None:
    """`decision` alanı beklenmeyen bir değer taşıyorsa da sonuç red olmalı — onay
    yalnızca modelin AÇIKÇA 'approved' demesiyle verilir."""
    agent_context.llm = StubLLMProvider(
        responses=[_IN_SCOPE, json.dumps({"decision": "belki"}), json.dumps({"decision": "belki"})]
    )
    agent = EditorAgent(agent_context)

    report = agent(EditorInput(article=_article()))

    assert report.decision is QADecision.REJECTED


def test_empty_body_raises(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE, _APPROVED])
    agent = EditorAgent(agent_context)

    with pytest.raises(AgentValidationError):
        agent(EditorInput(article=_article(body_markdown="   ")))


def test_retry_count_is_carried_into_report(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE, _APPROVED])
    agent = EditorAgent(agent_context)

    report = agent(EditorInput(article=_article(), retry_count=2))

    assert report.retry_count == 2


def test_rejects_writing_process_leftovers(agent_context: AgentContext) -> None:
    """Gerçek vaka (04.08.2026): Writer'ın genişletme talimatı metne sızdı ve makale
    '**Yeni paragraf:**' etiketleriyle YAYINLANDI — LLM incelemesi bunu onaylamıştı.
    Bu yüzden kontrol deterministik katmandadır."""
    body = _body(700) + "\n\n**Yeni paragraf:** Temizliği rutin hâle getirmek önemlidir."
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE, _APPROVED])
    agent = EditorAgent(agent_context)

    report = agent(EditorInput(article=_article(body_markdown=body)))

    assert report.decision is QADecision.REJECTED
    assert any("etiket kalıntısı" in reason for reason in report.reasons)


def test_legitimate_sentences_are_not_flagged_as_leftovers(agent_context: AgentContext) -> None:
    """Kalıp dar olmalı: 'yeni', 'bölüm', 'ek olarak' gibi sözcükler makalede meşru
    biçimde geçer ve bunlar reddedilmemeli."""
    body = (
        _body(700)
        + "\n\n## Yeni Bir Tahta Aldığınızda\n\nEk olarak, sirke de kullanabilirsiniz. "
        "Bu bölüm çok önemlidir: tahtayı iyice kurulayın."
    )
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE, _APPROVED])
    agent = EditorAgent(agent_context)

    report = agent(EditorInput(article=_article(body_markdown=body)))

    assert report.decision is QADecision.APPROVED


def test_word_count_bounds_follow_the_content_type(agent_context: AgentContext) -> None:
    """500 kelimelik bir TARİF geçer (taban 450), aynı uzunluktaki bir REHBER geçmez
    (taban 700). Tek bir global taban, tarifleri doğal uzunluklarının üstüne çıkmaya
    zorlayıp dolgu ürettiriyordu (07.08.2026)."""
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE, _APPROVED])
    recipe = _article(body_markdown=_body(500), content_type="recipe")

    report = EditorAgent(agent_context)(EditorInput(article=recipe))

    assert report.decision is QADecision.APPROVED


def test_guide_of_the_same_length_is_rejected_as_too_short(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE, _APPROVED])
    guide = _article(body_markdown=_body(500), content_type="guide")

    report = EditorAgent(agent_context)(EditorInput(article=guide))

    assert report.decision is QADecision.REJECTED
    assert "en az 700" in report.reasons[0]


def test_recipe_ceiling_is_lower_than_the_default(agent_context: AgentContext) -> None:
    """Tavan da tipe bağlı: 1000 kelimelik bir tarif artık tarif değildir (tavan 900),
    aynı uzunluk varsayılan bantta (1500) sorunsuz geçer."""
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE, _APPROVED])
    long_recipe = _article(body_markdown=_body(1000), content_type="recipe")

    report = EditorAgent(agent_context)(EditorInput(article=long_recipe))

    assert report.decision is QADecision.REJECTED
    assert "en fazla 900" in report.reasons[0]


def test_unknown_content_type_uses_brand_defaults(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE, _APPROVED])
    article = _article(body_markdown=_body(500), content_type="podcast")

    report = EditorAgent(agent_context)(EditorInput(article=article))

    assert report.decision is QADecision.REJECTED
    assert "en az 700" in report.reasons[0]
