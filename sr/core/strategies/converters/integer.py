"""整数转换器。"""

from sr.core.contracts.strategies import Converter


class Integer(Converter[int]):
    """整数与十进制文本互转。"""

    name = "int"

    def forward(self, text: str) -> int:
        """文本转整数。"""
        if type(text) is not str:
            raise TypeError("转换输入必须是 str")
        return int(text)

    def backward(self, value: int) -> str:
        """整数转文本。"""
        if type(value) is not int:
            raise TypeError("反向转换输入必须是 int")
        return str(value)
