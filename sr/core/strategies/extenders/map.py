"""原样传递字段的 map 拓展。"""

from collections.abc import Mapping
from types import MappingProxyType

from sr.core.contracts.extender import Extender
from sr.core.values import SystemValue, TokenValue


class Map(Extender):
    """不改变输入值的占位拓展。"""

    name = "map"
    input_ports = ("value",)
    output_ports = ("value",)

    def extend(
        self,
        input_values: Mapping[str, TokenValue],
        system_values: Mapping[str, SystemValue],
        *,
        options: Mapping[str, object] = MappingProxyType({}),
    ) -> Mapping[str, TokenValue]:
        """返回与输入等值的字段。"""
        value = input_values["value"].value
        return {"value": TokenValue(value=value, raw=value, operations=())}
