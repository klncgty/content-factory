"""Sistem çapında ortak logger.

Her agent kendi log satırlarını `get_logger(agent_adı)` ile yazar; tüm loggerlar
`content_factory` kök logger'ının altında hiyerarşiktir. `configure_logging` bir kez
(pipeline başında, brand + run_id ile) çağrılır; sonrasında yazılan her satır bu
run_id'yi taşır — bkz. ARCHITECTURE.md §16 (Gözlemlenebilirlik).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_ROOT_LOGGER_NAME = "content_factory"
_LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | brand=%(brand)s run_id=%(run_id)s | %(name)s | %(message)s"
)

_configured = False


class _ContextFilter(logging.Filter):
    """`brand`/`run_id` alanları record'da yoksa varsayılan değerle doldurur — böylece
    format string'i her zaman güvenle bu alanlara referans verebilir."""

    def __init__(self, brand: str, run_id: str) -> None:
        super().__init__()
        self._brand = brand
        self._run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "brand"):
            record.brand = self._brand
        if not hasattr(record, "run_id"):
            record.run_id = self._run_id
        return True


def configure_logging(
    *,
    brand: str | None = None,
    run_id: str | None = None,
    level: int = logging.INFO,
    log_dir: Path | None = None,
) -> logging.Logger:
    """Kök `content_factory` logger'ını yapılandırır. `log_dir` verilirse
    `{log_dir}/run.log` dosyasına da yazar (bkz. state/{brand}/runs/{run_id}/)."""
    global _configured

    root = logging.getLogger(_ROOT_LOGGER_NAME)
    root.setLevel(level)
    root.handlers.clear()
    root.propagate = False

    formatter = logging.Formatter(_LOG_FORMAT)
    context_filter = _ContextFilter(brand or "-", run_id or "-")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(context_filter)
    root.addHandler(console_handler)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "run.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.addFilter(context_filter)
        root.addHandler(file_handler)

    _configured = True
    return root


def get_logger(name: str) -> logging.Logger:
    """`content_factory.{name}` altında bir child logger döndürür. `configure_logging`
    henüz çağrılmadıysa makul varsayılanlarla (yalnızca konsol) otomatik yapılandırır."""
    if not _configured:
        configure_logging()
    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{name}")
