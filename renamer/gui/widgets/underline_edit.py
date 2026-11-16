"""下划线行内名称编辑框基类：顶栏标题与词流词名共用的编辑体验

统一行为：
- 宽度跟随文本，下划线（控件宽）输入增长实时、删除不变短，失焦退出时按文本收口；
- 进入编辑记录「上一次提交值」；退出编辑（回车或失焦）时内容为空视为放弃改名，
  回显该值；
- 回车确认本次编辑并结束编辑态（失焦），长度策略由子类各自设定。
"""

from PySide6.QtCore import QSize
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QLineEdit

__all__ = ["UnderlineEdit"]


class UnderlineEdit(QLineEdit):
    """下划线行内名称编辑基类"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._editing = False
        self._floor_w = 0  # 编辑期到过的最宽文本（防删除时下划线实时变短）
        self._prev_text = ""  # 进入编辑时的已提交值（空退出据此回显）
        self.textChanged.connect(self._on_text_changed)
        self.returnPressed.connect(self._on_return)

    def _text_width(self) -> int:
        fm = QFontMetrics(self.font())
        text = self.text()
        return fm.horizontalAdvance(text) if text else 0

    def _on_text_changed(self) -> None:
        # 编辑中只抬高下限不降低：增长实时、删字不实时收窄，缩短留到失焦
        if self._editing:
            self._floor_w = max(self._floor_w, self._text_width())
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        w = self._text_width()
        if self._editing:
            w = max(w, self._floor_w)
        return QSize(w + 2, super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    # 编辑态生命周期
    def focusInEvent(self, event) -> None:
        # 以当前文本宽为下限；增长由 _on_text_changed 抬高；快照供空退出回显
        self._editing = True
        self._floor_w = self._text_width()
        self._prev_text = self.text()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self._end_edit()
        super().focusOutEvent(event)

    def _on_return(self) -> None:
        """回车：先按收尾规则处理（空回显上次值），再结束编辑态（失焦收口）"""
        self._settle()
        self.clearFocus()

    def _settle(self) -> None:
        """编辑收尾：内容为空且之前有值则放弃改名，回显上次提交值"""
        if not self.text().strip() and self._prev_text.strip():
            self.setText(self._prev_text)

    def _end_edit(self) -> None:
        """失焦退出：空值回显上次提交值，再切回展示态"""
        if not self._editing:
            return
        self._settle()
        self._reset_display()

    def settle_display(self) -> None:
        """外部强制收成展示态（不回显空值）：供重建词流后归位"""
        self._reset_display()

    def _reset_display(self) -> None:
        """回到展示态的公共收口：解除编辑态与宽度下限、光标回行首"""
        self._editing = False
        self._floor_w = 0
        self.setCursorPosition(0)
        self.updateGeometry()
