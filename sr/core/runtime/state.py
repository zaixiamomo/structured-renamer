"""文件在管线中的不可变状态。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from sr.core.compile.token import CompiledToken
from sr.core.errors import FileError

if TYPE_CHECKING:
    from sr.core.compile.rule import CompiledRule
    from sr.core.compile.template_branch import CompiledTemplateBranch
    from sr.core.values import TokenValue


@dataclass(frozen=True, slots=True)
class FileState:
    """单文件在匹配、分组、选择、扩展和组合阶段之间的不可变快照。"""

    rule: CompiledRule | None = None
    parse: CompiledTemplateBranch | None = None
    captures: Mapping[str, TokenValue] | None = None
    group: tuple[Path, ...] = ()
    render: CompiledTemplateBranch | None = None
    values: Mapping[str, TokenValue] | None = None
    result: str | None = None
    error: FileError | None = None
    path: Path | None = None

    def __post_init__(self) -> None:
        """冻结容器并校验阶段字段的一致性。"""
        # 统一为绝对路径，后续按 Path 判等和分组。
        if self.path is not None:
            object.__setattr__(self, "path", self.path.absolute())
        for name in ("captures", "values"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, MappingProxyType(dict(value)))
        object.__setattr__(self, "group", tuple(self.group))

        matched = (
            self.rule is not None,
            self.parse is not None,
            self.captures is not None,
        )
        if any(matched) and not all(matched):
            raise ValueError("匹配信息必须完整")

        if self.render is not None and (self.rule is None or not self.group):
            raise ValueError("选择正文前必须完成匹配和分组")

        if self.values is not None:
            if self.render is None:
                raise ValueError("准备字段前必须选定正文")
            names = {
                part.name
                for part in self.render.template.parts
                if isinstance(part, CompiledToken)
            }
            if self.values.keys() != names:
                raise ValueError("字段必须完整对应所选正文")

        if self.result is not None and self.values is None:
            raise ValueError("生成结果前必须完成字段准备")
