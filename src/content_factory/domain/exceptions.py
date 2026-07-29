"""Tüm agent'ların ortak kullandığı exception hiyerarşisi.

`LLMError` (bkz. `providers/llm/exceptions.py`) ile karıştırılmamalı: o katman
sağlayıcı/ağ hatalarını temsil eder, bu modül ise **agent'ın kendi iş mantığı**
seviyesindeki hataları temsil eder (yapılandırma eksikliği, LLM yanıtının
ayrıştırılamaması, girdi doğrulama vb.). Bir agent, `LLMError`'ı yakalayıp
`AgentOutputParsingError` gibi kendi hata tipine çevirmek isteyebilir — ikisi de
`AgentError`'dan türemez, kasıtlı olarak ayrı hiyerarşilerdir (katman ayrımı net kalsın diye).
"""

from __future__ import annotations


class AgentError(Exception):
    """Tüm agent-seviyesi hataların temel sınıfı."""


class AgentValidationError(AgentError):
    """`BaseAgent.validate()` tarafından geçersiz girdi için fırlatılır."""


class AgentConfigurationError(AgentError):
    """Agent'ın çalışması için gereken bir bağımlılık (provider, config alanı vb.)
    `AgentContext`'e enjekte edilmemiş veya yapılandırılmamış."""


class AgentOutputParsingError(AgentError):
    """LLM yanıtı, agent'ın beklediği yapılandırılmış (ör. JSON) forma ayrıştırılamadı."""
