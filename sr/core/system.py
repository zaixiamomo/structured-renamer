"""文件系统字段声明与读取。"""

from collections.abc import Callable, Mapping
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from sr.core.errors import PipelineError
from sr.core.values import SystemValue

if TYPE_CHECKING:
    from sr.core.runtime.state import FileState


class SystemField(Enum):
    """可绑定到拓展端口的文件系统字段。"""

    FILE_PATH = "file.path", Path, lambda f: f.path
    FILE_NAME = "file.name", str, lambda f: f.path.name
    FILE_STEM = "file.stem", str, lambda f: f.path.stem
    FILE_SUFFIX = "file.suffix", str, lambda f: f.path.suffix.lower()
    FILE_PARENT = "file.parent", Path, lambda f: f.path.parent
    FILE_PARENT_NAME = "file.parent_name", str, lambda f: f.path.parent.name
    GROUP_MEMBERS = "group.members", tuple, lambda f: f.group
    RULE_NAME = "rule.name", str, lambda f: f.rule.name if f.rule is not None else None

    def __new__(cls, name, value_type, reader):
        """把枚举值与值类型、读取函数一起注册。"""
        # 枚举成员直接携带类型和读取器，省去额外的字段表。
        instance = object.__new__(cls)
        instance._value_ = name
        instance.value_type = value_type
        instance.reader = reader
        return instance

    value_type: type
    reader: Callable[["FileState"], SystemValue]

    def read(self, file: "FileState | None") -> SystemValue:
        """读取字段值。

        Args:
            file: 已完成来源绑定的 FileState。
        Returns:
            字段对应的路径、文本或组成员。
        Raises:
            PipelineError: 上下文缺失、文件信息未就绪或字段为空。
        """
        if file is None or file.path is None:
            raise PipelineError("系统字段需要已固定路径的文件上下文")
        value = self.reader(file)
        if value is None or (self is SystemField.GROUP_MEMBERS and not value):
            raise PipelineError(f"系统字段 {self.value} 所需的文件信息尚未就绪")
        return value

    def accepts(self, value: SystemValue) -> bool:
        """判断值是否符合字段声明的类型。"""
        if self is SystemField.GROUP_MEMBERS:
            return isinstance(value, tuple) and all(isinstance(p, Path) for p in value)
        return isinstance(value, self.value_type)


def check_system_bindings(
    declaration: Mapping[str, SystemField],
) -> Mapping[str, SystemField]:
    """校验并冻结端口到 SystemField 的映射。

    Args:
        declaration: 端口名到 SystemField 的映射。
    Returns:
        声明内容的只读副本。
    Raises:
        TypeError: 声明或字段来源类型不符。
        ValueError: 端口名不是合法标识符。
    """
    if not isinstance(declaration, Mapping):
        raise TypeError("system_bindings 必须是端口到 SystemField 的映射")
    for port, source in declaration.items():
        if not isinstance(port, str) or not port.isidentifier():
            raise ValueError("系统输入端口必须是合法标识符")
        if not isinstance(source, SystemField):
            raise TypeError("系统输入来源必须是 SystemField")
    return MappingProxyType(dict(declaration))


def read_system_values(
    declaration: Mapping[str, SystemField], file: "FileState"
) -> Mapping[str, SystemValue]:
    """按声明读取一个文件的全部系统字段。

    Args:
        declaration: 端口到 SystemField 的映射。
        file: 当前调用使用的文件状态。
    Returns:
        端口到字段值的只读映射。
    Raises:
        PipelineError: 字段不可读或类型不符。
    """
    values = {}
    for port, field in check_system_bindings(declaration).items():
        value = field.read(file)
        if not field.accepts(value):
            raise PipelineError(
                f"系统输入 {port} 类型错误，需要 {field.value_type.__name__}"
            )
        values[port] = value
    return MappingProxyType(values)
