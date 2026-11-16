"""抽屉动画期的面板静态快照：按自身宽度裁取快照左缘绘制"""

from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

__all__ = ["DrawerShot"]


class DrawerShot(QWidget):
    """抽屉动画期的面板静态快照"""

    def __init__(self, pm: QPixmap, parent=None):
        super().__init__(parent)
        self._pm = pm
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        # 画整张快照锚定 (0,0)，画布外部分由绘制系统裁剪，等价左缘裁切
        painter.drawPixmap(0, 0, self._pm)
