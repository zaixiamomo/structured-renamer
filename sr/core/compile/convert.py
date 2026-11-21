"""convert 转换器 DSL 的编译。"""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from sr.core.contracts.compilable import Compilable
from sr.core.contracts.strategies import Converter
from sr.core.strategies import CONVERTERS


@dataclass(frozen=True)
class CompiledConvert:
    """已选定的值转换器。"""

    converter: Converter

    def forward(self, text: str) -> object:
        """文本转值。"""
        return self.converter.forward(text)

    def backward(self, value: object) -> str:
        """值转文本。"""
        return self.converter.backward(value)


class Convert(BaseModel, Compilable[CompiledConvert]):
    """按名称选择转换器的声明。"""

    text: str

    model_config = ConfigDict(frozen=True, extra="forbid")

    def __init__(self, text: str) -> None:
        """接受转换器名称。"""
        super().__init__(text=text)

    def compile(self) -> CompiledConvert:
        """实例化声明名称对应的转换器。

        Raises:
            ValueError: 转换器名称未知。
        """
        name = self.text.strip()
        converter_type = CONVERTERS.get(name)
        if converter_type is None:
            raise ValueError(f"未知转换类型：{name}")
        return CompiledConvert(converter_type())
