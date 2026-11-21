"""扩展节点声明与执行产物。"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, Field

from sr.core.compile.token import CompiledToken, Token
from sr.core.contracts.compilable import Compilable
from sr.core.contracts.extender import Extender
from sr.core.system import check_system_bindings
from sr.core.values import SystemValue, TokenValue


@dataclass(frozen=True, eq=False)
class CompiledExtension:
    """一次拓展调用的编译产物。"""

    name: str
    inputs: Mapping[str, CompiledToken]
    outputs: Mapping[str, CompiledToken]
    options: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))

    def execute(
        self,
        token_values: Mapping[str, TokenValue],
        extender: Extender,
        system_values: Mapping[str, SystemValue],
    ) -> Mapping[str, TokenValue]:
        """执行拓展并整理输出字段。

        Args:
            token_values: 当前文件中输入词段的求值结果。
            extender: 对应的运行实例。
            system_values: 已读取的系统字段。
        Returns:
            输出词段名到新 TokenValue 的只读映射。
        Raises:
            ValueError: 返回的输出端口与声明不一致。
            TypeError: 输出不是 TokenValue。
        """
        input_values: dict[str, TokenValue] = {}
        for port, token in self.inputs.items():
            # 输入端口只取词段的计算值，raw 与旧加工链不带入拓展。
            value = token.apply(token_values[token.name].value, convert=False)
            input_values[port] = TokenValue(value=value, raw=value, operations=())
        output_values = extender.extend(
            MappingProxyType(input_values),
            MappingProxyType(dict(system_values)),
            options=self.options,
        )
        # 只要求覆盖声明端口，允许拓展返回额外字段。
        if not set(self.outputs) <= set(output_values):
            raise ValueError("拓展返回的输出端口与声明不一致")
        result: dict[str, TokenValue] = {}
        for port, token in self.outputs.items():
            output = output_values[port]
            if not isinstance(output, TokenValue):
                raise TypeError("拓展输出必须是 TokenValue")
            # 拓展自身的加工链在前，输出词段的加工链在后。
            result[token.name] = TokenValue(
                value=token.apply(output.value, convert=False),
                raw=output.raw,
                operations=(*output.operations, *token.transform.cleaners),
            )
        return MappingProxyType(result)


class Extension(BaseModel, Compilable[CompiledExtension]):
    """拓展调用的声明。"""

    name: str
    inputs: dict[str, Token] = Field(default_factory=dict)
    outputs: dict[str, Token]
    options: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True, extra="forbid")

    def compile(
        self,
        *,
        extenders: Mapping[str, type[Extender]] | None = None,
    ) -> CompiledExtension:
        """校验端口并编译输入/输出词段。

        Args:
            extenders: 完整能力名到拓展类的映射。
        Returns:
            CompiledExtension；options 已递归冻结。
        Raises:
            ValueError: 拓展未知、端口不匹配或输出词段名重复。
        """
        registry = {} if extenders is None else extenders
        extender_type = registry.get(self.name)
        if extender_type is None:
            raise ValueError(f"未知拓展：{self.name}")
        check_system_bindings(extender_type.system_bindings)
        if set(self.inputs) != set(extender_type.input_ports):
            raise ValueError("拓展输入端口与策略签名不一致")
        if not set(self.outputs) <= set(extender_type.output_ports):
            raise ValueError("拓展输出端口与策略签名不一致")
        input_bindings = {
            port: token.compile("convert") for port, token in self.inputs.items()
        }
        output_bindings = {
            port: token.compile("convert") for port, token in self.outputs.items()
        }
        targets = [token.name for token in output_bindings.values()]
        if len(targets) != len(set(targets)):
            raise ValueError("拓展输出 token 名不能重复")
        return CompiledExtension(
            name=self.name,
            inputs=MappingProxyType(input_bindings),
            outputs=MappingProxyType(output_bindings),
            options=MappingProxyType(
                {name: _freeze_option(value) for name, value in self.options.items()}
            ),
        )


def _freeze_option(value: object) -> object:
    """递归把选项容器转为不可变形式。"""
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze_option(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_option(item) for item in value)
    return value
