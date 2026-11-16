"""领域插件声明：字段、命名解析模板、能力元数据与实现工厂"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from renamer.core.model import Capability, CapabilityFn, Field, Template
from renamer.core.ports import HttpClient

__all__ = ["BuildCalls", "Domain", "NamedParseTemplate"]

# 注册名称独立于模板对象，与 Library.parse_templates 的键含义一致
NamedParseTemplate = tuple[str, Template]

BuildCalls = Callable[[HttpClient | None], Mapping[str, CapabilityFn]]


def _no_calls(getter: HttpClient | None = None) -> Mapping[str, CapabilityFn]:
    return {}


@dataclass(frozen=True)
class Domain:
    """领域元数据与能力实现工厂，供注册表查询和装配"""

    name: str
    fields: tuple[Field, ...] = ()
    parse_templates: tuple[NamedParseTemplate, ...] = ()
    capabilities: tuple[Capability, ...] = ()
    build_calls: BuildCalls = _no_calls
