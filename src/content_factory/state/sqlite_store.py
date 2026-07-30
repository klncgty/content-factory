"""`StateStore`'un SQLite implementasyonu (bkz. ARCHITECTURE.md §12: neden SQLite).

Bu dosya dışında hiçbir modül `sqlite3`'ü import etmez — agent'lar yalnızca
`content_factory.state.store.StateStore` arayüzünü bilir.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from content_factory.domain.models import (
    Article,
    ArticleStatus,
    ImageData,
    InternalLinkRecord,
    ScopeRejectionRecord,
    SEOData,
    Topic,
)
from content_factory.state.store import StateStore
from content_factory.utils.logging import get_logger

_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand TEXT NOT NULL,
    slug TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT,
    target_keyword TEXT,
    secondary_keywords_json TEXT NOT NULL DEFAULT '[]',
    body_markdown TEXT NOT NULL DEFAULT '',
    article_date TEXT,
    updated_date TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    tags_json TEXT NOT NULL DEFAULT '[]',
    reading_time_minutes INTEGER,
    related_articles_json TEXT NOT NULL DEFAULT '[]',
    commit_sha TEXT,
    file_path TEXT,
    word_count INTEGER,
    seo_json TEXT,
    image_json TEXT,
    UNIQUE (brand, slug)
);

CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand TEXT NOT NULL,
    keyword TEXT NOT NULL,
    article_slug TEXT NOT NULL,
    UNIQUE (brand, keyword)
);

CREATE TABLE IF NOT EXISTS topics_backlog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT,
    seed_keywords_json TEXT NOT NULL DEFAULT '[]',
    score REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    created_run_id TEXT
);

CREATE TABLE IF NOT EXISTS internal_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand TEXT NOT NULL,
    source_article_id INTEGER,
    target_article_id INTEGER,
    source_slug TEXT NOT NULL,
    target_slug TEXT NOT NULL,
    link_type TEXT NOT NULL DEFAULT 'related_section',
    created_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE,
    brand TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    topic_id INTEGER,
    article_id INTEGER,
    error TEXT
);

CREATE TABLE IF NOT EXISTS scope_rejections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    brand TEXT NOT NULL,
    stage TEXT NOT NULL,
    reason TEXT NOT NULL,
    payload_snippet TEXT NOT NULL DEFAULT ''
);
"""

# Bu sürüm, yukarıdaki _SCHEMA'nın karşılık geldiği şemayı temsil eder. Yeni bir
# şema değişikliği gerektiğinde: (1) _SCHEMA'yı güncelle, (2) sürümü 1 artır,
# (3) eski DB'leri yeni sürüme taşıyacak ALTER/UPDATE deyimlerini _MIGRATIONS'a
# yeni anahtar olarak ekle. PRAGMA user_version sayesinde her migration bir kez
# uygulanır; var olan veriler silinmez veya bozulmaz.
_SCHEMA_VERSION = 1

_MIGRATIONS: dict[int, list[str]] = {
    # Örnek: 2: ["ALTER TABLE articles ADD COLUMN foo TEXT"],
}


class SQLiteStateStore(StateStore):
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._logger = get_logger("state.sqlite")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

    # -- şema -------------------------------------------------------------------------
    def init_schema(self) -> None:
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

        current_version = self._conn.execute("PRAGMA user_version").fetchone()[0]

        if current_version == 0:
            # Ya taze bir DB (tablolar az önce _SCHEMA ile oluşturuldu) ya da bu
            # migration mekanizmasından önce oluşmuş eski bir DB — her iki
            # durumda da mevcut yapı zaten baseline şemayla eşleşiyor.
            current_version = _SCHEMA_VERSION
            self._conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            self._conn.commit()

        if current_version > _SCHEMA_VERSION:
            raise RuntimeError(
                f"DB şema sürümü ({current_version}) koddan ({_SCHEMA_VERSION}) daha "
                "yeni; uygulamayı güncelleyin."
            )

        for version in range(current_version + 1, _SCHEMA_VERSION + 1):
            for statement in _MIGRATIONS.get(version, []):
                self._conn.execute(statement)
            self._conn.execute(f"PRAGMA user_version = {version}")
            self._conn.commit()

    # -- articles ---------------------------------------------------------------------
    def record_article(self, article: Article) -> int:
        params = (
            article.brand,
            article.slug,
            article.title,
            article.description,
            article.category,
            article.target_keyword,
            json.dumps(article.secondary_keywords, ensure_ascii=False),
            article.body_markdown,
            article.date.isoformat() if article.date else None,
            article.updated.isoformat() if article.updated else None,
            article.status.value,
            json.dumps(article.tags, ensure_ascii=False),
            article.reading_time_minutes,
            json.dumps(article.related_articles, ensure_ascii=False),
            article.commit_sha,
            article.file_path,
            article.word_count,
            article.seo.model_dump_json() if article.seo else None,
            article.image.model_dump_json() if article.image else None,
        )
        self._conn.execute(
            """
            INSERT INTO articles (
                brand, slug, title, description, category, target_keyword,
                secondary_keywords_json, body_markdown, article_date, updated_date,
                status, tags_json, reading_time_minutes, related_articles_json,
                commit_sha, file_path, word_count, seo_json, image_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(brand, slug) DO UPDATE SET
                title=excluded.title, description=excluded.description,
                category=excluded.category, target_keyword=excluded.target_keyword,
                secondary_keywords_json=excluded.secondary_keywords_json,
                body_markdown=excluded.body_markdown, article_date=excluded.article_date,
                updated_date=excluded.updated_date, status=excluded.status,
                tags_json=excluded.tags_json, reading_time_minutes=excluded.reading_time_minutes,
                related_articles_json=excluded.related_articles_json,
                commit_sha=excluded.commit_sha, file_path=excluded.file_path,
                word_count=excluded.word_count, seo_json=excluded.seo_json,
                image_json=excluded.image_json
            """,
            params,
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT id FROM articles WHERE brand = ? AND slug = ?", (article.brand, article.slug)
        ).fetchone()
        return int(row["id"])

    def get_recent_articles(self, brand: str, limit: int = 20) -> list[Article]:
        rows = self._conn.execute(
            "SELECT * FROM articles WHERE brand = ? ORDER BY article_date DESC, id DESC LIMIT ?",
            (brand, limit),
        ).fetchall()
        return [_row_to_article(row) for row in rows]

    def find_related_articles(
        self,
        brand: str,
        keywords: list[str],
        *,
        category: str | None = None,
        exclude_slug: str | None = None,
        limit: int = 5,
    ) -> list[Article]:
        rows = self._conn.execute(
            "SELECT * FROM articles WHERE brand = ? AND (? IS NULL OR slug != ?)",
            (brand, exclude_slug, exclude_slug),
        ).fetchall()
        candidates = [_row_to_article(row) for row in rows]

        keyword_set = {k.lower() for k in keywords}

        def score(article: Article) -> tuple[int, int]:
            article_keywords = {article.target_keyword.lower()} if article.target_keyword else set()
            article_keywords |= {k.lower() for k in article.secondary_keywords}
            overlap = len(keyword_set & article_keywords)
            category_match = 1 if category and article.category == category else 0
            return (overlap, category_match)

        candidates.sort(key=score, reverse=True)
        return candidates[:limit]

    def slug_exists(self, brand: str, slug: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM articles WHERE brand = ? AND slug = ?", (brand, slug)
        ).fetchone()
        return row is not None

    # -- keywords -----------------------------------------------------------------
    def is_keyword_used(self, brand: str, keyword: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM keywords WHERE brand = ? AND keyword = ?", (brand, keyword)
        ).fetchone()
        return row is not None

    def record_keyword_usage(self, brand: str, keyword: str, article_slug: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO keywords (brand, keyword, article_slug) VALUES (?, ?, ?)",
            (brand, keyword, article_slug),
        )
        self._conn.commit()

    # -- topics backlog -------------------------------------------------------------
    def add_topic_candidates(self, topics: list[Topic]) -> None:
        rows = [
            (
                t.brand,
                t.title,
                t.category,
                json.dumps(t.seed_keywords, ensure_ascii=False),
                t.score,
                t.status,
                t.created_run_id,
            )
            for t in topics
        ]
        self._conn.executemany(
            """INSERT INTO topics_backlog
               (brand, title, category, seed_keywords_json, score, status, created_run_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        self._conn.commit()

    def get_pending_topics(self, brand: str, limit: int = 10) -> list[Topic]:
        rows = self._conn.execute(
            """SELECT * FROM topics_backlog WHERE brand = ? AND status = 'pending'
               ORDER BY score DESC, id ASC LIMIT ?""",
            (brand, limit),
        ).fetchall()
        return [
            Topic(
                id=row["id"],
                brand=row["brand"],
                title=row["title"],
                category=row["category"],
                seed_keywords=json.loads(row["seed_keywords_json"]),
                score=row["score"],
                status=row["status"],
                created_run_id=row["created_run_id"],
            )
            for row in rows
        ]

    def mark_topic_status(self, topic_id: int, status: str) -> None:
        self._conn.execute(
            "UPDATE topics_backlog SET status = ? WHERE id = ?", (status, topic_id)
        )
        self._conn.commit()

    # -- internal links ---------------------------------------------------------------
    def record_internal_link(self, link: InternalLinkRecord) -> None:
        source_row = self._conn.execute(
            "SELECT id FROM articles WHERE brand = ? AND slug = ?", (link.brand, link.source_slug)
        ).fetchone()
        target_row = self._conn.execute(
            "SELECT id FROM articles WHERE brand = ? AND slug = ?", (link.brand, link.target_slug)
        ).fetchone()
        self._conn.execute(
            """INSERT INTO internal_links
               (brand, source_article_id, target_article_id, source_slug, target_slug,
                link_type, created_run_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                link.brand,
                source_row["id"] if source_row else None,
                target_row["id"] if target_row else None,
                link.source_slug,
                link.target_slug,
                link.link_type,
                link.created_run_id,
            ),
        )
        self._conn.commit()

    # -- runs ---------------------------------------------------------------------------
    def start_run(self, run_id: str, brand: str) -> None:
        self._conn.execute(
            "INSERT INTO runs (run_id, brand, started_at, status) VALUES (?, ?, ?, 'running')",
            (run_id, brand, datetime.now().isoformat()),
        )
        self._conn.commit()

    def finish_run(self, run_id: str, status: str, error: str | None = None) -> None:
        self._conn.execute(
            "UPDATE runs SET status = ?, finished_at = ?, error = ? WHERE run_id = ?",
            (status, datetime.now().isoformat(), error, run_id),
        )
        self._conn.commit()

    # -- scope audit -----------------------------------------------------------------
    def log_scope_rejection(self, rejection: ScopeRejectionRecord) -> None:
        self._conn.execute(
            """INSERT INTO scope_rejections (run_id, brand, stage, reason, payload_snippet)
               VALUES (?, ?, ?, ?, ?)""",
            (
                rejection.run_id,
                rejection.brand,
                rejection.stage,
                rejection.reason,
                rejection.payload_snippet,
            ),
        )
        self._conn.commit()

    # -- lifecycle ------------------------------------------------------------------------
    def close(self) -> None:
        self._conn.close()


def _row_to_article(row: sqlite3.Row) -> Article:
    return Article(
        id=row["id"],
        brand=row["brand"],
        slug=row["slug"],
        title=row["title"],
        description=row["description"],
        category=row["category"],
        target_keyword=row["target_keyword"],
        secondary_keywords=json.loads(row["secondary_keywords_json"]),
        body_markdown=row["body_markdown"],
        date=date.fromisoformat(row["article_date"]) if row["article_date"] else None,
        updated=date.fromisoformat(row["updated_date"]) if row["updated_date"] else None,
        status=ArticleStatus(row["status"]),
        tags=json.loads(row["tags_json"]),
        reading_time_minutes=row["reading_time_minutes"],
        related_articles=json.loads(row["related_articles_json"]),
        commit_sha=row["commit_sha"],
        file_path=row["file_path"],
        word_count=row["word_count"],
        seo=SEOData.model_validate_json(row["seo_json"]) if row["seo_json"] else None,
        image=ImageData.model_validate_json(row["image_json"]) if row["image_json"] else None,
    )
