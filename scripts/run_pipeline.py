#!/usr/bin/env python3
"""İnce sarmalayıcı — ARCHITECTURE.md'de belgelenen `scripts/run_pipeline.py` yolu.

Gerçek implementasyon `content_factory.cli.main`'dedir (`uv run content-factory
--brand oleart` ile de çalıştırılabilir; bu script yalnızca dosya yoluna dayalı
alışıldık girişi sağlar).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from content_factory.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
