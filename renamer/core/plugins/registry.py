"""按注册顺序查询领域元数据并装配能力实现"""

from __future__ import annotations

from renamer.core.model import Capability, CapabilityFn, Field, FieldKey, Template
from renamer.core.ports import HttpClient

from .domain import Domain, NamedParseTemplate

__all__ = ["DomainRegistry"]


class DomainRegistry:
    """显式持有领域集合，提供元数据查询和能力实现装配"""

    def __init__(self, domains: tuple[Domain, ...] = ()) -> None:
        self._domains = tuple(domains)

    def list_domains(self) -> list[Domain]:
        """全部已注册领域（按注册序）"""
        return list(self._domains)

    def list_capabilities(self, implemented_only: bool = False) -> list[Capability]:
        """按注册顺序列出能力；筛选已实现能力时调用无 HTTP 的实现工厂"""
        caps: list[Capability] = []
        for domain in self._domains:
            caps.extend(domain.capabilities)
        if implemented_only:
            available = set(self.build_calls())
            return [cap for cap in caps if cap.id in available and cap.implemented]
        return caps

    def list_parse_templates(self) -> list[NamedParseTemplate]:
        """按领域注册顺序列出解析模板的名称与对象"""
        templates: list[NamedParseTemplate] = []
        for domain in self._domains:
            templates.extend(domain.parse_templates)
        return templates

    def capabilities_by_id(self) -> dict[str, Capability]:
        """供编译使用的能力表，同名由后注册者覆盖，保留首次出现的位置"""
        return {cap.id: cap for cap in self.list_capabilities()}

    def fields_by_key(self) -> dict[FieldKey, Field]:
        """按领域注册顺序合并字段，同名由后注册者覆盖"""
        return {field.key: field for domain in self._domains for field in domain.fields}

    def build_calls(self, http: HttpClient | None = None) -> dict[str, CapabilityFn]:
        """按领域注册顺序装配能力实现，同名能力由后注册的领域覆盖"""
        calls: dict[str, CapabilityFn] = {}
        for domain in self._domains:
            calls.update(domain.build_calls(http))
        return calls

    def find_parse_template(self, name: str) -> Template | None:
        """查找首个同名解析模板，不进行编译或执行"""
        for template_name, template in self.list_parse_templates():
            if template_name == name:
                return template
        return None
