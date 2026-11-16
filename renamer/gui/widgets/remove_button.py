"""内容移除共用按钮：统一删除符号、点击区域和主题样式。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QWidget


class RemoveButton(QPushButton):
    """以用途说明区分删除、移除和解除绑定，外观保持一致。"""

    def __init__(self, tooltip: str, parent: QWidget | None = None) -> None:
        super().__init__("✕", parent)
        self.setProperty("role", "tok-del")
        self.setFixedSize(20, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
