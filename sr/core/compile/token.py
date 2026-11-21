"""词段表达式与编译产物。"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, ModelWrapValidatorHandler, model_validator

from sr.core.compile.classify import Classify, CompiledClassify
from sr.core.compile.convert import CompiledConvert, Convert
from sr.core.compile.transform import CompiledTransform, Transform
from sr.core.contracts.compilable import Compilable

TokenUsage = Literal["transform", "convert"]


@dataclass(frozen=True)
class CompiledToken:
    """可应用加工、分类或转换的词段。"""

    name: str
    classify: CompiledClassify | None
    convert: CompiledConvert | None = None
    transform: CompiledTransform | None = None

    def apply(self, text: str, convert: bool = False) -> object:
        """对文本应用加工链，并按需转换。

        Args:
            text: 待处理文本。
            convert: 为 True 且声明了转换器时返回值而非 str。
        Returns:
            加工后的文本或转换后的值。
        Raises:
            TypeError: text 不是 str，或加工结果不是 str。
        """
        if type(text) is not str:
            raise TypeError("词段输入必须是 str")
        if self.transform is not None:
            text = self.transform.clean(text)
        if convert and self.convert is not None:
            return self.convert.forward(text)
        return text

    def matches(self, char: str) -> bool:
        """判断字符是否属于词段类别。

        Args:
            char: 待判断的单个字符。
        Returns:
            命中类别时为 True。
        Raises:
            ValueError: convert 用途的词段没有字符类别。
        """
        if self.classify is None:
            raise ValueError("convert 词段不支持字符类别匹配")
        return self.classify.matches(char)


class Token(BaseModel, Compilable[CompiledToken]):
    """name[=qualifier][:transform] 形式的词段声明。"""

    name: str
    qualifier: str | None
    transform: Transform

    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="wrap")
    @classmethod
    def _parse_expression(
        cls, value: object, handler: ModelWrapValidatorHandler["Token"]
    ) -> "Token":
        """让字符串直接走 Token.__init__，其余交给 pydantic。"""
        if isinstance(value, str):
            return cls(value)
        if isinstance(value, dict) and "expression" in value:
            raise ValueError("词段请直接使用字符串，不支持 expression 包装")
        return handler(value)

    def __init__(self, expression: str) -> None:
        """解析词段表达式。

        Args:
            expression: ``name[=qualifier][:transform]``；qualifier 分别是捕获类别或转换器。
        Raises:
            TypeError: 表达式不是 str。
            ValueError: 名称不是合法标识符。
        """
        if not isinstance(expression, str):
            raise TypeError("词段必须是字符串")

        # 冒号前是名称和限定符，冒号后是加工链。
        declaration, _, transform = expression.partition(":")
        name, separator, qualifier = declaration.partition("=")
        name = name.strip()

        if not name.isidentifier():
            raise ValueError(f"非法词段名称：{name!r}，系统属性不能作为普通 token 使用")

        super().__init__(
            name=name,
            qualifier=qualifier if separator else None,
            transform=Transform(transform),
        )

    def compile(self, usage: TokenUsage) -> CompiledToken:
        """按用途编译词段。

        Args:
            usage: transform 用于模板捕获，convert 用于分组和拓展端口。
        Returns:
            CompiledToken；convert 用途会附加转换器。
        Raises:
            ValueError: 忽略词段用于 convert，或用途未知。
        """
        if usage == "transform":
            return self._compile_transform()
        if usage == "convert":
            if self.name == "_":
                raise ValueError("忽略词段只能用于 parse 模板")
            return self._compile_convert()
        raise ValueError(f"未知词段用途：{usage!r}")

    def _compile_transform(self) -> CompiledToken:
        """编译捕获用词段；无 qualifier 时不限制字符类别。"""
        return CompiledToken(
            name=self.name,
            classify=(
                Classify(self.qualifier).compile()
                if self.qualifier is not None
                else CompiledClassify(())
            ),
            convert=None,
            transform=self.transform.compile(),
        )

    def _compile_convert(self) -> CompiledToken:
        """编译转换用词段；无 qualifier 时不做类型转换。"""
        return CompiledToken(
            name=self.name,
            classify=None,
            convert=(
                Convert(self.qualifier).compile()
                if self.qualifier is not None
                else None
            ),
            transform=self.transform.compile(),
        )
