"""İçerik kapsamı garantisi — bkz. ARCHITECTURE.md §2.

Bu bir agent değildir; Orchestrator tarafından TopicScout çıktısına (pre_check, tamamen
deterministik, LLM çağrısı yapmaz) ve EditorAgent'ın QA aşamasında (post_check, LLM
sınıflandırıcı) karşı çağrılır. `pre_check` saf anahtar kelime eşleştirmesi olduğu için
hiçbir LLM çağrısı yapmaz; `post_check` `BaseLLMProvider` üzerinden gerçek bir
sınıflandırma çağrısı yapar (bkz. `prompts/scope_guard/`).
"""

from __future__ import annotations

from pydantic import BaseModel

from content_factory.domain.exceptions import AgentOutputParsingError
from content_factory.domain.models import ScopeDecision
from content_factory.prompts.loader import PromptLoader
from content_factory.providers.llm import BaseLLMProvider, LLMMessage, LLMRequest
from content_factory.settings.schemas import ScopeConfig
from content_factory.utils.json_llm import parse_llm_json

_ARTICLE_EXCERPT_MAX_CHARS = 4000
"""LLM çağrı maliyetini sınırlamak için makalenin yalnızca ilk N karakteri gönderilir —
kapsam kayması genellikle makalenin geneline yayılır, tam metin gerekmez."""


class ScopeCheckResult(BaseModel):
    decision: ScopeDecision
    matched_group: str | None = None
    reason: str


class ScopeGuard:
    def __init__(self, scope_config: ScopeConfig) -> None:
        self._scope = scope_config

    def pre_check(self, *, title: str, seed_keywords: list[str]) -> ScopeCheckResult:
        """Deterministik anahtar kelime eşleştirmesi — `scope.yaml groups[].topics`'e karşı.
        Hiçbir LLM çağrısı yapmaz (bkz. ARCHITECTURE.md §2 tablosu)."""
        haystack = " ".join([title, *seed_keywords]).lower()
        for group in self._scope.groups:
            for topic in group.topics:
                if topic.lower() in haystack:
                    return ScopeCheckResult(
                        decision=ScopeDecision.IN_SCOPE,
                        matched_group=group.id,
                        reason=f"'{topic}' anahtar kelimesiyle eşleşti",
                    )
        return ScopeCheckResult(
            decision=ScopeDecision.OUT_OF_SCOPE,
            reason="scope.yaml içindeki hiçbir grup/anahtar kelimeyle eşleşmedi",
        )

    def post_check(
        self,
        *,
        article_body: str,
        llm: BaseLLMProvider,
        prompt_loader: PromptLoader,
        model: str,
        run_id: str,
    ) -> ScopeCheckResult:
        """EditorAgent'ın QA gate'inin bir parçası — draft'ı `scope.yaml groups[].id`
        veya `"out_of_scope"` olarak sınıflandırır (`out_of_scope_examples` few-shot
        negatif örnek olarak kullanılır). `pre_check`'ten farklı olarak Writer'ın
        konudan ustaca sapmasını (ör. genel sağlık tavsiyesine kayması) yakalayabilir."""
        prompts = prompt_loader.load("scope_guard")

        groups_description = "\n".join(
            f"- `{g.id}` ({g.label}): {', '.join(g.topics)}" for g in self._scope.groups
        )
        out_of_scope_examples = "\n".join(f"- {ex}" for ex in self._scope.out_of_scope_examples)
        article_excerpt = article_body.strip()[:_ARTICLE_EXCERPT_MAX_CHARS]

        user_message = prompts.render_user(
            groups_description=groups_description,
            out_of_scope_examples=out_of_scope_examples,
            article_excerpt=article_excerpt,
        )
        request = LLMRequest(
            system_prompt=prompts.system,
            messages=[LLMMessage(role="user", content=user_message)],
            model=model,
            temperature=0.0,
            max_tokens=300,
        )
        response = llm.generate(request, agent_name="scope_guard", run_id=run_id)
        data = parse_llm_json(response.content, agent_name="scope_guard")

        if not isinstance(data, dict) or "group_id" not in data:
            raise AgentOutputParsingError(
                "scope_guard: LLM yanıtında 'group_id' alanı bulunamadı"
            )

        group_id = str(data["group_id"])
        reason = str(data.get("reason", ""))
        valid_group_ids = {g.id for g in self._scope.groups}

        if group_id == "out_of_scope" or group_id not in valid_group_ids:
            return ScopeCheckResult(decision=ScopeDecision.OUT_OF_SCOPE, reason=reason)
        return ScopeCheckResult(
            decision=ScopeDecision.IN_SCOPE, matched_group=group_id, reason=reason
        )
