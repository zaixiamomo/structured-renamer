"""按别名表映射字段的 lookup 拓展。"""

from collections.abc import Mapping

from sr.core.contracts.extender import Extender
from sr.core.values import SystemValue, TokenValue


class Lookup(Extender):
    """把输入值替换为 options 中命中的目标值。"""

    name = "lookup"
    input_ports = ("value",)
    output_ports = ("value",)

    def extend(
        self,
        input_values: Mapping[str, TokenValue],
        system_values: Mapping[str, SystemValue],
        *,
        options: Mapping[str, object],
    ) -> Mapping[str, TokenValue]:
        """按 options 的 target -> aliases 表替换输入值。

        Args:
            input_values: 必须包含 value 端口。
            system_values: 系统字段值；lookup 不使用。
            options: 目标值到别名列表的映射；别名必须全局唯一。
        Returns:
            value 端口的新 TokenValue，raw 沿用输入。
        Raises:
            ValueError: options 为空、结构非法、别名冲突或未命中。
        """
        # 反向索引别名，顺便检测一个别名指向多个目标。
        aliases_to_targets: dict[str, str] = {}
        if not options:
            raise ValueError("lookup options 不能为空")
        for target, aliases in options.items():
            if not isinstance(target, str) or not target:
                raise ValueError("lookup 目标必须是非空字符串")
            if not isinstance(aliases, (list, tuple)) or not aliases:
                raise ValueError(f"目标 {target!r} 的别名必须是非空列表")
            for alias in aliases:
                if not isinstance(alias, str) or not alias:
                    raise ValueError(f"目标 {target!r} 的别名必须是非空字符串")
                previous = aliases_to_targets.setdefault(alias, target)
                if previous != target:
                    raise ValueError(
                        f"别名 {alias!r} 同时属于 {previous!r} 和 {target!r}"
                    )
        source = input_values["value"]
        try:
            value = aliases_to_targets[source.value]
        except KeyError as exc:
            raise ValueError(f"映射未命中：{source.value!r}") from exc
        return {"value": TokenValue(value=value, raw=source.raw, operations=())}
