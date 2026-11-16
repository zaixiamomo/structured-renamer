"""行内名称编辑框（顶栏标题）：宽度跟随文本，下划线恰好压住文本，无显式编辑框感"""

from PySide6.QtWidgets import QSizePolicy

from .underline_edit import UnderlineEdit

__all__ = ["InlineEdit"]


class InlineEdit(UnderlineEdit):
    """顶栏标题名称编辑框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # 水平 Preferred：宽度仍跟随文本（有剩余空间时不撑满），但空间不足时可收缩，
        # 由行内 textChanged/左侧对齐截断右侧超长文本，而不是把整行撑出可视区
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
