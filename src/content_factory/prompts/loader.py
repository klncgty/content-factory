"""Prompt sistemi — her LLM kullanan agent'ın promptu `prompts/{agent}/` altında ayrı
dosyalarda tutulur (`system.md`, `user.md`, `examples.md`). Hiçbir agent prompt
metnini kendi Python kodunda taşımaz; hepsi `PromptLoader.load(agent_name)` çağırır.

Tasarım, `content_factory.knowledge.loader.KnowledgeLoader` ile bilinçli olarak
aynı desende: marka başına değil, agent başına cache'lenen bir dosya seti +
`invalidate()`. İki yükleyici arasında kod paylaşımı yok çünkü kavramsal olarak
farklı şeyler yüklüyorlar (biri marka bilgisini, diğeri agent talimatlarını) — ama
aynı desen, projedeki herkesin ikisini de aynı şekilde okuyup anlayabilmesini sağlar.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from string import Template

from content_factory.utils.logging import get_logger
from content_factory.utils.paths import project_root

_logger = get_logger("prompts.loader")

_FILES = ("system.md", "user.md", "examples.md")


@dataclass(frozen=True)
class PromptSet:
    """Bir agent'ın tüm prompt materyali. `user_template`, `render_user(**vars)` ile
    doldurulur — eksik/fazla bir değişken `string.Template.substitute` ile KeyError
    fırlatır (agent kodu ile `user.md` şablonu arasındaki sözleşme sessizce bozulmaz;
    bkz. `BaseAgent.prompt_vars` ve tests/test_prompts.py)."""

    agent: str
    system: str
    user_template: str
    examples: str

    def render_user(self, **variables: str) -> str:
        return Template(self.user_template).substitute(**variables)


class PromptLoader:
    def __init__(self, root: Path | None = None, *, brand: str | None = None) -> None:
        self._root = root or project_root()
        # Marka verilirse `brands/{marka}/prompts/` DOSYA BAZINDA öncelik kazanır:
        # markanın kendi `system.md`'si varsa o kullanılır, `user.md`'si yoksa ortak
        # olana düşülür. Dosya bazında olması önemli — markaya özgü olan genellikle
        # yalnızca "sen kimsin/neyi kapsıyorsun" kısmıdır, JSON şeması değil.
        self._brand = brand
        self._cache: dict[str, PromptSet] = {}
        self._lock = threading.Lock()

    def agent_dir(self, agent_name: str) -> Path:
        return self._root / "prompts" / agent_name

    def brand_agent_dir(self, agent_name: str) -> Path | None:
        if self._brand is None:
            return None
        return self._root / "brands" / self._brand / "prompts" / agent_name

    def resolve_file(self, agent_name: str, filename: str) -> Path | None:
        """Bir prompt dosyasının fiilen okunacağı yol: önce markaya özgü, sonra ortak.
        Hiçbiri yoksa `None`."""
        brand_dir = self.brand_agent_dir(agent_name)
        if brand_dir is not None and (brand_path := brand_dir / filename).exists():
            return brand_path
        shared_path = self.agent_dir(agent_name) / filename
        return shared_path if shared_path.exists() else None

    def load(self, agent_name: str, *, force_reload: bool = False) -> PromptSet:
        with self._lock:
            if not force_reload and agent_name in self._cache:
                return self._cache[agent_name]
            prompt_set = self._read_from_disk(agent_name)
            self._cache[agent_name] = prompt_set
            return prompt_set

    def invalidate(self, agent_name: str | None = None) -> None:
        with self._lock:
            if agent_name is None:
                self._cache.clear()
            else:
                self._cache.pop(agent_name, None)

    def _read_from_disk(self, agent_name: str) -> PromptSet:
        values: dict[str, str] = {}
        for filename in _FILES:
            path = self.resolve_file(agent_name, filename)
            if path is None:
                _logger.warning(f"prompt dosyası eksik agent={agent_name} file={filename}")
                values[filename] = ""
                continue
            values[filename] = path.read_text(encoding="utf-8")
        return PromptSet(
            agent=agent_name,
            system=values["system.md"],
            user_template=values["user.md"],
            examples=values["examples.md"],
        )
