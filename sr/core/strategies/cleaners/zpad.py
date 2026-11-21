"""零填充清洗器。"""

from sr.core.contracts.strategies import Cleaner


class Zpad(Cleaner):
    """用 0 左补齐到指定宽度。"""

    name = "zpad"

    def __init__(self, width: int) -> None:
        """校验补齐宽度。

        Args:
            width: 0 到 10000 之间的整数。
        Raises:
            TypeError: width 不是 int。
            ValueError: width 越界。
        """
        if type(width) is not int:
            raise TypeError("zpad 宽度必须是整数")
        if not 0 <= width <= 10000:
            raise ValueError("zpad 宽度必须在 0 到 10000 之间")
        self.width = width

    def _clean(self, text: str) -> str:
        """按固定宽度左补零。"""
        # 空字段不补零，否则会凭空生成 "000"。
        return text.zfill(self.width) if text else ""
