"""规则文档与编译入口。"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, field_validator

from sr.core.compile.extension import CompiledExtension, Extension
from sr.core.compile.group import CompiledGroup, Group
from sr.core.compile.template import TemplateUsage
from sr.core.compile.template_branch import CompiledTemplateBranch, TemplateBranch
from sr.core.compile.transform import Transform
from sr.core.contracts.compilable import Compilable
from sr.core.contracts.extender import Extender


@dataclass(frozen=True)
class CompiledRule:
    """规则编译后的匹配、渲染和分组数据。"""

    name: str
    parse: tuple[CompiledTemplateBranch, ...]
    render: tuple[CompiledTemplateBranch, ...]
    group: tuple[CompiledGroup, ...] | None = None
    # 生产者表以输出词段名为键，同一名称可有多个候选节点。
    producers: Mapping[str, tuple[CompiledExtension, ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )


class Rule(BaseModel, Compilable[CompiledRule]):
    """一条完整的 YAML 规则声明。"""

    name: str
    transform: Mapping[TemplateUsage, Transform] | None = None
    parse: tuple[TemplateBranch, ...]
    render: tuple[TemplateBranch, ...]
    group: tuple[Group, ...] | None = None
    extensions: tuple[Extension, ...] = ()

    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator("group", mode="before")
    @classmethod
    def _group_entries(cls, value: object) -> object:
        """允许单个 Group 简写为一项。"""
        return (value,) if isinstance(value, Group) else value

    def compile(
        self,
        *,
        extenders: Mapping[str, type[Extender]] | None = None,
    ) -> CompiledRule:
        """编译整条规则。

        Args:
            extenders: 完整能力名到拓展类的映射；存在拓展声明时必须提供。
        Returns:
            CompiledRule；生产者按输出词段名建立索引。
        Raises:
            ValueError: 分支、分组或拓展声明不合法。
            SyntaxError: 分支表达式语法错误。
        """
        transform = self.transform or {}
        parse = tuple(
            branch.compile("parse", default_transform=transform.get("parse"))
            for branch in self.parse
        )
        render = tuple(
            branch.compile("render", default_transform=transform.get("render"))
            for branch in self.render
        )
        group = tuple(entry.compile() for entry in self.group) if self.group else None
        producers: dict[str, list[CompiledExtension]] = {}
        for extension in self.extensions:
            # 同一输出词段可由多个拓展候选生产，运行时再按 supports() 过滤。
            compiled = extension.compile(extenders=extenders)
            for token in compiled.outputs.values():
                producers.setdefault(token.name, []).append(compiled)

        return CompiledRule(
            name=self.name,
            parse=parse,
            render=render,
            group=group,
            producers=MappingProxyType(
                {name: tuple(nodes) for name, nodes in producers.items()}
            ),
        )
