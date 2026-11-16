"""领域插件声明与注册表"""

from __future__ import annotations

from .domain import BuildCalls, Domain, NamedParseTemplate
from .registry import DomainRegistry

__all__ = ["BuildCalls", "Domain", "DomainRegistry", "NamedParseTemplate"]
