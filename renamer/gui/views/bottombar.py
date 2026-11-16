"""底栏：左侧文件树计数，右侧执行结果统计"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QWidget

from ..theme import T, ThemeManager
from ..widgets.center_guide import DebugCenterGuide
from ..widgets.optical_label import OpticalLabel

__all__ = ["BottomBar"]


class BottomBar(QWidget):
    """底栏"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("bottomBar")
        # 同顶栏：border-radius 的 QSS 底色需要显式 WA_StyledBackground 才绘制
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(16)

        self._sel = OpticalLabel("")
        self._sel.setProperty("role", "status-left")
        lay.addWidget(self._sel)

        lay.addStretch(1)

        # 执行结果统计：置于 stretch 之后即最右侧
        self._run = OpticalLabel("")
        self._run.setProperty("role", "status-run")
        lay.addWidget(self._run)
        self._center_guide = DebugCenterGuide(self)

        # 统计状态缓存：主题热切换时重建彩色统计文字（颜色取自 T()）
        self._stats: tuple[int, int, int] | None = None
        self._msg: str | None = None
        ThemeManager.instance().theme_changed.connect(self._rebuild_run_info)

    def set_counts(self, total: int, selected: int) -> None:
        """显示文件树总文件数与复选框已选文件数"""
        self._sel.setText(f"总文件 {total} / {selected} 已选中")

    def set_run_info(self, stats: tuple[int, int, int] | None) -> None:
        """显示执行结果统计（ok, warn, fail）；None 清空"""
        self._stats = stats
        self._msg = None
        self._rebuild_run_info()

    def _rebuild_run_info(self) -> None:
        """按缓存统计重建分段文字（颜色来自当前系列 T()）"""
        if self._msg is not None:
            return  # 临时消息优先，主题切换不覆盖
        if self._stats is None:
            self._run.setText("")
            return
        ok, warn, fail = self._stats
        self._run.set_colored_text(
            [
                ("●", QColor(T("color.ok"))),
                (f" 成功 {ok}\u00a0\u00a0", None),
                ("●", QColor(T("color.warn"))),
                (f" 警告 {warn}\u00a0\u00a0", None),
                ("●", QColor(T("color.err"))),
                (f" 失败 {fail}", None),
            ]
        )

    def set_message(self, text: str) -> None:
        """显示临时消息（如撤回提示）"""
        self._msg = text
        self._run.setText(text)
