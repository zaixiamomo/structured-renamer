"""编译和运行时共享的值对象。"""

from dataclasses import dataclass
from pathlib import Path

from sr.core.contracts.strategies import Cleaner, Converter

# 系统字段可产生的值类型。
SystemValue = str | Path | tuple[Path, ...]


@dataclass(frozen=True)
class TokenValue:
    """字段值及其原始文本、加工链。"""

    value: str
    raw: str
    operations: tuple[Cleaner | Converter, ...]

    def __post_init__(self) -> None:
        """把加工链规范为元组。"""
        object.__setattr__(self, "operations", tuple(self.operations))


@dataclass(frozen=True)
class LiteralText:
    """模板中的字面量片段。"""

    text: str
