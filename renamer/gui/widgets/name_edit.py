"""词段名输入（卡片2 词流）：宽度跟随文本，下划线恰好压住文本，字体主色"""

from PySide6.QtWidgets import QSizePolicy

from .underline_edit import UnderlineEdit

__all__ = ["NameEdit"]


class NameEdit(UnderlineEdit):
    """词段名输入"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
