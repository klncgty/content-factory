"""YAML frontmatter'lı markdown dosyalarını ayrıştırma/üretme.

Yayın sözleşmesinin (ARCHITECTURE.md §6) dosya biçimi tarafı burada tek bir yerde
yaşar: `PublisherAgent` hem yeni makaleyi üretmek hem de LinkerAgent'ın planladığı
`related_articles` güncellemeleri için eski makaleleri okuyup geri yazmak üzere bu
modülü kullanır.

Ayrıştırma bilinçli olarak toleranslıdır: frontmatter yoksa ya da bozuksa hata
fırlatılmaz, boş bir alan sözlüğü ve dosyanın tamamı gövde olarak döner — tek bir
bozuk eski makale yüzünden yayın akışı durmamalıdır (çağıran taraf bu durumu
`fields` boş geldiğinde fark eder).
"""

from __future__ import annotations

from typing import Any

import yaml

_DELIMITER = "---"


def split(text: str) -> tuple[dict[str, Any], str]:
    """`(frontmatter_alanları, gövde)` döndürür."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != _DELIMITER:
        return {}, text

    for index in range(1, len(lines)):
        if lines[index].strip() == _DELIMITER:
            raw = "\n".join(lines[1:index])
            body = "\n".join(lines[index + 1 :]).lstrip("\n")
            try:
                fields = yaml.safe_load(raw) or {}
            except yaml.YAMLError:
                return {}, text
            return (fields, body) if isinstance(fields, dict) else ({}, text)

    return {}, text


def render(fields: dict[str, Any], body: str) -> str:
    """`fields` sözlüğünü **verildiği sırayla** frontmatter'a yazar (`sort_keys=False`):
    sözleşmedeki alan sırası okunabilirlik için anlamlıdır ve alfabetik sıralama onu
    bozar. `default_flow_style=None`, `secondary_keywords: [a, b]` gibi düz listelerin
    tek satırda kalmasını sağlar."""
    dumped = yaml.safe_dump(
        fields, allow_unicode=True, sort_keys=False, default_flow_style=None
    ).strip()
    return f"{_DELIMITER}\n{dumped}\n{_DELIMITER}\n\n{body.strip()}\n"
