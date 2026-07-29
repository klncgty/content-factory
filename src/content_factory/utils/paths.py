"""Proje kökünü bulma — `settings` ve `knowledge` modüllerinin ortak kullandığı tek yer.

İki bağımsız "kökü bul" implementasyonu, biri güncellenip diğeri unutulduğunda sessizce
birbirinden sapabilir (ör. testlerde `CONTENT_FACTORY_ROOT` override'ı bir yerde
uygulanır, diğerinde uygulanmaz). Bu yüzden tek bir yerden çözümlenir.
"""

from __future__ import annotations

import os
from pathlib import Path

# paths.py -> utils/ -> content_factory/ -> src/ -> <repo kökü>
# Bu ilişki src layout'un bir parçasıdır; dosya taşınmadıkça sabittir.
_PACKAGE_ROOT = Path(__file__).resolve().parents[3]


def project_root() -> Path:
    """content-factory reposunun kökü. Testlerde/izole ortamlarda
    `CONTENT_FACTORY_ROOT` env değişkeniyle override edilebilir."""
    override = os.environ.get("CONTENT_FACTORY_ROOT")
    return Path(override).resolve() if override else _PACKAGE_ROOT
