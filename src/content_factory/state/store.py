"""Kalıcı state için repository (soyutlama) arayüzü.

Hiçbir agent SQLite (veya ileride Postgres) bilmez — yalnızca bu `StateStore` arayüzünü
kullanır. Somut implementasyon `content_factory.state.sqlite_store.SQLiteStateStore`'dur
(bkz. ARCHITECTURE.md §12). İleride Postgres'e geçiş, yalnızca yeni bir `StateStore`
implementasyonu eklemeyi gerektirir — bu arayüz ve onu kullanan agent kodu değişmez.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType

from content_factory.domain.models import (
    Article,
    InternalLinkRecord,
    LLMCallRecord,
    ScopeRejectionRecord,
    Topic,
)


class StateStore(ABC):
    # -- şema -----------------------------------------------------------------------
    @abstractmethod
    def init_schema(self) -> None:
        """Tablolar yoksa oluşturur. Idempotent olmalıdır."""

    # -- articles ---------------------------------------------------------------------
    @abstractmethod
    def record_article(self, article: Article) -> int:
        """Makaleyi kalıcılaştırır, oluşturulan kaydın id'sini döndürür."""

    @abstractmethod
    def get_recent_articles(self, brand: str, limit: int = 20) -> list[Article]: ...

    @abstractmethod
    def find_related_articles(
        self,
        brand: str,
        keywords: list[str],
        *,
        category: str | None = None,
        exclude_slug: str | None = None,
        limit: int = 5,
    ) -> list[Article]:
        """LinkerAgent'ın kullandığı benzerlik sorgusu — v1'de anahtar kelime/kategori
        örtüşmesi, Faz 3'te embedding-tabanlı benzerliğe geçirilebilir (implementasyon
        detayı, bu arayüz değişmez)."""

    @abstractmethod
    def slug_exists(self, brand: str, slug: str) -> bool: ...

    # -- keywords -----------------------------------------------------------------
    @abstractmethod
    def is_keyword_used(self, brand: str, keyword: str) -> bool:
        """Keyword cannibalization kontrolü — bkz. brands/{brand}/seo.yaml notu."""

    @abstractmethod
    def record_keyword_usage(self, brand: str, keyword: str, article_slug: str) -> None: ...

    # -- topics backlog -------------------------------------------------------------
    @abstractmethod
    def add_topic_candidates(self, topics: list[Topic]) -> None: ...

    @abstractmethod
    def get_pending_topics(self, brand: str, limit: int = 10) -> list[Topic]: ...

    @abstractmethod
    def mark_topic_status(self, topic_id: int, status: str) -> None: ...

    # -- internal links ---------------------------------------------------------------
    @abstractmethod
    def record_internal_link(self, link: InternalLinkRecord) -> None: ...

    # -- runs ---------------------------------------------------------------------------
    @abstractmethod
    def start_run(self, run_id: str, brand: str) -> None: ...

    @abstractmethod
    def finish_run(self, run_id: str, status: str, error: str | None = None) -> None: ...

    # -- scope audit (bkz. ARCHITECTURE.md §2) -----------------------------------------
    @abstractmethod
    def log_scope_rejection(self, rejection: ScopeRejectionRecord) -> None: ...

    # -- llm çağrıları (bkz. ARCHITECTURE.md §16) --------------------------------------
    @abstractmethod
    def record_llm_call(self, call: LLMCallRecord) -> None:
        """Her başarılı LLM çağrısını (model, token, süre) kaydeder — run başına
        token/maliyet görünürlüğü `get_run_llm_calls` ile sağlanır."""

    @abstractmethod
    def get_run_llm_calls(self, run_id: str) -> list[LLMCallRecord]: ...

    # -- lifecycle ------------------------------------------------------------------------
    @abstractmethod
    def close(self) -> None: ...

    def __enter__(self) -> StateStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
