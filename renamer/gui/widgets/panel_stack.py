"""面板栈：宽收敛到 0、高随「当前页」内容最小高，卡片随视图重排

宽向仍取所有页的最大（抽屉宽度下限须容纳任何一扇窗口的卡片全可见），高向
只取当前页的最小高：各窗口面板共享同一滚动区，若高取全部页最大值，隐藏的
高页会把当前页顶出滚动态——内容明明不需要滚轮却出现幻影滚动区/滚动条。
切页时的滚动位置按窗口存档/还原由 SidePanel 负责，本类不持状态。

QStackedLayout 的 heightForWidth()/hasHeightForWidth() 会把**全部页**（含隐藏）
一起算（取最大）。QScrollArea 判分支时读内部 layout 的 hasHeightForWidth（拦不住），
但真正取值走 widget 级 heightForWidth —— 因此这里覆写 widget 级两个查询，
把「需要多高」改成只问当前页；否则只要同时存在模板与规则窗，任何一页都会被
顶到最高页的高度。
"""

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QStackedWidget

__all__ = ["PanelStack"]


class PanelStack(QStackedWidget):
    """面板栈"""

    def sizeHint(self) -> QSize:
        page = self.currentWidget()
        h = page.minimumSizeHint().height() if page is not None else 0
        return QSize(0, h)

    def minimumSizeHint(self) -> QSize:
        w = 0
        h = 0
        cur = self.currentWidget()
        for i in range(self.count()):
            page = self.widget(i)
            if page is None:
                continue
            w = max(w, page.minimumSizeHint().width())
            if page is cur:
                h = page.minimumSizeHint().height()
        return QSize(w, h)

    # 高度相关查询只问当前页（见模块 docstring）
    def hasHeightForWidth(self) -> bool:
        page = self.currentWidget()
        return page is not None and page.hasHeightForWidth()

    def heightForWidth(self, width: int) -> int:
        page = self.currentWidget()
        if page is not None and page.hasHeightForWidth():
            return page.heightForWidth(width)
        return -1

    def current_content_height(self, width: int) -> int:
        """当前页在给定宽度下需要的滚动内容高：minSizeHint 与 heightForWidth 取大"""
        page = self.currentWidget()
        if page is None:
            return 0
        h = page.minimumSizeHint().height()
        if page.hasHeightForWidth() and width > 0:
            h = max(h, page.heightForWidth(width))
        return h
