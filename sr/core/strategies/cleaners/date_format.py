"""日期格式转换清洗器。"""

from datetime import datetime

from sr.core.contracts.strategies import Cleaner

# 只放行常见 strftime/strptime 指令，避免平台差异和意外格式。
_DIRECTIVES = frozenset("aAbBcdHIjmMpSUwWxXyYfzZGVu%")


class DateFormat(Cleaner):
    """按输入格式解析日期，再按输出格式渲染。"""

    name = "date_format"

    def __init__(self, input_format: str, output_format: str) -> None:
        """校验并保存日期格式。

        Args:
            input_format: datetime.strptime 使用的格式。
            output_format: datetime.strftime 使用的格式。
        Raises:
            TypeError: 格式不是字符串。
            ValueError: 格式为空或含不支持的指令。
        """
        for value in (input_format, output_format):
            if type(value) is not str:
                raise TypeError("date_format 的输入和输出格式必须是字符串")
            if not value.strip():
                raise ValueError("date_format 的输入和输出格式不能为空")
            position = 0
            while position < len(value):
                if value[position] == "%":
                    position += 1
                    if position == len(value) or value[position] not in _DIRECTIVES:
                        raise ValueError(f"date_format 不支持的格式指令：{value!r}")
                position += 1
        self.input_format = input_format
        self.output_format = output_format

    def _clean(self, text: str) -> str:
        """解析输入格式并按输出格式重排。"""
        value = datetime.strptime(text, self.input_format)
        return value.strftime(self.output_format)
