"""插件拓展的运行契约。"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar

from sr.core.system import SystemField
from sr.core.values import SystemValue

if TYPE_CHECKING:
    from sr.core.values import TokenValue


class Extender(ABC):
    """向规则提供额外字段的生产者。"""

    name: ClassVar[str]
    input_ports: ClassVar[tuple[str, ...]]
    output_ports: ClassVar[tuple[str, ...]]
    system_bindings: ClassVar[Mapping[str, SystemField]] = MappingProxyType({})
    required_resources: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def create(cls, *, resources: Mapping[str, object]) -> "Extender":
        """创建批次共享的能力实例。

        有资源需求的子类须重写此方法，返回的实例应支持不同组并发调用。

        Args:
            resources: 按 required_resources 选出的借用资源，由装配方关闭。
        Returns:
            Extender 实例。
        """
        return cls()

    def supports(self, system_values: Mapping[str, SystemValue]) -> bool:
        """判断能力是否适用于当前文件或组。

        Args:
            system_values: 按 system_bindings 读取的系统字段。
        Returns:
            为 False 时跳过该能力；执行失败不能解释为不适用。
        """
        return True

    @abstractmethod
    def extend(
        self,
        input_values: Mapping[str, "TokenValue"],
        system_values: Mapping[str, SystemValue],
        *,
        options: Mapping[str, object],
    ) -> Mapping[str, "TokenValue"]:
        """由输入字段和系统值产出输出字段。

        同一实例可能被不同组并发调用，实现不得在实例中保存调用数据。

        Args:
            input_values: 输入端口到 TokenValue 的映射。
            system_values: system_bindings 声明的系统字段值。
            options: 规则中为该拓展提供的常量选项。
        Returns:
            输出端口到 TokenValue 的映射，必须覆盖声明过的输出端口。
        Raises:
            ValueError: 输入或选项不满足能力要求。
        """
        ...
