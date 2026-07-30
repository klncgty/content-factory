"""config/*.yaml ve brands/{brand}/*.yaml dosyalarını okuyup tipli `Settings` nesnesine
dönüştürür. Agent'lar YAML/dosya sistemi hakkında hiçbir şey bilmez — yalnızca bu modülün
ürettiği `Settings` nesnesini kullanır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from content_factory.settings.schemas import (
    BrandConfig,
    EngineConfig,
    KnowledgeConfig,
    ModelsConfig,
    PublishConfig,
    ScheduleConfig,
    ScopeConfig,
    SeoConfig,
)
from content_factory.utils.paths import project_root


class ConfigError(RuntimeError):
    """Bir config dosyası bulunamadığında veya şemaya uymadığında fırlatılır."""


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"Config dosyası bulunamadı: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data or {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """`override`'daki değerleri `base` üzerine iç içe (recursive) olarak uygular."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@dataclass(frozen=True)
class Settings:
    """Belirli bir marka için çözümlenmiş tüm konfigürasyonun tek giriş noktası.

    Kullanım: ``settings = Settings.load("oleart")`` — sonrasında ``settings.brand``,
    ``settings.scope``, ``settings.models`` vb. ile erişilir.
    """

    root: Path
    brand_name: str
    engine: EngineConfig
    models: ModelsConfig
    brand: BrandConfig
    scope: ScopeConfig
    publish: PublishConfig
    seo: SeoConfig
    schedule: ScheduleConfig
    knowledge: KnowledgeConfig

    # knowledge/brands/{brand}/ — sabit bir sistem geneli kural, brand.yaml'da
    # yapılandırılmaz (bkz. content_factory.knowledge.loader.KnowledgeLoader, ki o da
    # bu path'i bağımsız olarak aynı kuralla çözümler).
    knowledge_dir: Path = field(init=False)
    prompts_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        knowledge_dir = self.root / "knowledge" / "brands" / self.brand_name
        prompts_dir = self.root / "brands" / self.brand_name / "prompts"
        object.__setattr__(self, "knowledge_dir", knowledge_dir)
        object.__setattr__(self, "prompts_dir", prompts_dir)

    @classmethod
    def load(cls, brand: str, *, root: Path | None = None) -> Settings:
        root = root or project_root()
        brand_dir = root / "brands" / brand
        if not brand_dir.is_dir():
            raise ConfigError(f"Marka dizini bulunamadı: {brand_dir}")

        engine = EngineConfig.model_validate(_load_yaml(root / "config" / "engine.yaml"))

        models_data = _load_yaml(root / "config" / "models.yaml")
        brand_models_path = brand_dir / "models.yaml"
        if brand_models_path.exists():
            models_data = _deep_merge(models_data, _load_yaml(brand_models_path))
        models = ModelsConfig.model_validate(models_data)

        brand_config = BrandConfig.model_validate(_load_yaml(brand_dir / "brand.yaml"))
        scope = ScopeConfig.model_validate(_load_yaml(brand_dir / brand_config.scope_file))
        publish = PublishConfig.model_validate(_load_yaml(brand_dir / "publish.yaml"))
        seo = SeoConfig.model_validate(_load_yaml(brand_dir / "seo.yaml"))
        schedule = ScheduleConfig.model_validate(_load_yaml(brand_dir / "schedule.yaml"))
        knowledge = KnowledgeConfig.model_validate(_load_yaml(brand_dir / "knowledge.yaml"))

        return cls(
            root=root,
            brand_name=brand,
            engine=engine,
            models=models,
            brand=brand_config,
            scope=scope,
            publish=publish,
            seo=seo,
            schedule=schedule,
            knowledge=knowledge,
        )

    def resolve(self, path_template: str, **extra: str) -> Path:
        """``engine.yaml``'daki ``{brand}``/``{run_id}`` gibi şablonları kökten çözümler."""
        return self.root / path_template.format(brand=self.brand_name, **extra)

    def target_repo_path(self) -> Path:
        """publish.yaml: target_repo_path — content-factory köküne göre çözümlenir."""
        return (self.root / self.publish.target_repo_path).resolve()
