from __future__ import annotations

import pytest
from pydantic import BaseModel

from content_factory.agents.base import AgentContext, BaseAgent


class _EchoInput(BaseModel):
    value: str


class _EchoAgent(BaseAgent[_EchoInput, str]):
    name = "topic_scout"  # config/models.yaml içinde tanımlı bir rol kullanıyoruz

    def run(self, input_data: _EchoInput) -> str:
        return input_data.value.upper()


def test_base_agent_cannot_be_instantiated_directly(agent_context: AgentContext) -> None:
    with pytest.raises(TypeError):
        BaseAgent(agent_context)  # type: ignore[abstract]


def test_concrete_agent_call_runs_and_logs(agent_context: AgentContext) -> None:
    agent = _EchoAgent(agent_context)
    assert agent(_EchoInput(value="merhaba")) == "MERHABA"


def test_load_config_reads_models_yaml(agent_context: AgentContext) -> None:
    """Agent'ın config'i, marka override'ı uygulanmış hâliyle okuduğunu doğrular.

    Beklenen model adı burada sabitlenmez: `brands/oleart/models.yaml` bir model/maliyet
    ayar dosyasıdır ve değişmesi normaldir — sabitlemek testi her ayar değişikliğinde
    kırıyordu. Doğrulanan davranış "aynı çözümlenmiş config'i okuyor" olmalı."""
    agent = _EchoAgent(agent_context)
    config = agent.load_config()
    assert config.model == agent_context.settings.models.for_agent("topic_scout").model
    assert config.model
