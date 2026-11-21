"""分组声明与编译产物。"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sr.core.compile.partition import CompiledPartition, Partition
from sr.core.compile.token import CompiledToken, Token
from sr.core.contracts.compilable import Compilable
from sr.core.values import TokenValue


@dataclass(frozen=True)
class CompiledGroup:
    """按词段转换值划分组员的编译产物。"""

    token: CompiledToken
    partition: CompiledPartition

    def split(self, values: Mapping[Path, TokenValue]) -> tuple[tuple[Path, ...], ...]:
        """按转换后的字段值划分成员。

        Returns:
            若干成员路径元组。
        Raises:
            ValueError: 字段值无法转换。
        """
        converted = {
            path: self.token.apply(value.value, convert=True)
            for path, value in values.items()
        }
        return self.partition.split(converted)


class Group(BaseModel, Compilable[CompiledGroup]):
    """选择分组词段与划分器的声明。"""

    token: Token
    partition: Partition = Field(default_factory=lambda: Partition("equal"))

    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator("partition", mode="before")
    @classmethod
    def _parse_partition(cls, value: object) -> object:
        """允许用字符串简写划分器。"""
        return Partition(value) if isinstance(value, str) else value

    def compile(self) -> CompiledGroup:
        """编译分组词段和划分器。

        Returns:
            包含转换用词段和已编译划分器的产物。
        Raises:
            ValueError: 词段或划分器编译失败。
        """
        token = self.token.compile("convert")
        return CompiledGroup(
            token=token,
            partition=self.partition.compile(),
        )
