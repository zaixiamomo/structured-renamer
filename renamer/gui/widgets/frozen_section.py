"""滚动分区：上下边缘冻结、原位占位、分隔线和圆角共用实现。"""

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from .editor_card import EditorCard


class FrozenSection(QObject):
    def __init__(
        self, owner: QWidget, holder: QWidget, panes: list[QWidget], *, edge: str
    ):
        super().__init__(owner)
        if edge not in ("top", "bottom"):
            raise ValueError("edge must be top or bottom")
        self._owner, self._holder, self._panes = owner, holder, panes
        self._edge = edge
        self._enabled = False
        self._scroll_area: QScrollArea | None = None
        self.card = QWidget(owner)
        self.card.setProperty("role", "frozen-section")
        self.card.setProperty("edge", edge)
        self.card.setProperty("state", "seat")
        self.card.setProperty("corner", "square")
        self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.body = QVBoxLayout(self.card)
        margin = EditorCard.CONTENT_MARGIN_X
        self.body.setContentsMargins(margin, 8, margin, 8)
        self.body.setSpacing(8)
        self.card.hide()
        self._divider = QFrame(owner)
        self._divider.setProperty("role", "frozen-divider")
        self._divider.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._divider.setFixedHeight(1)
        self._divider.hide()
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.timeout.connect(self.update)
        owner.installEventFilter(self)
        holder.installEventFilter(self)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.update()

    def attach_scroll_area(self, scroll_area: QScrollArea) -> None:
        if self._scroll_area is scroll_area:
            return
        if self._scroll_area is not None:
            bar = self._scroll_area.verticalScrollBar()
            bar.valueChanged.disconnect(self.update)
            bar.rangeChanged.disconnect(self.update)
            self._scroll_area.viewport().removeEventFilter(self)
        self._scroll_area = scroll_area
        scroll_area.verticalScrollBar().valueChanged.connect(self.update)
        scroll_area.verticalScrollBar().rangeChanged.connect(self.update)
        scroll_area.viewport().installEventFilter(self)
        self.update()

    def update(self) -> None:
        """按指定视口边缘冻结，保留原位占位和卡片外沿。"""
        card = self.card
        holder = self._holder
        divider = self._divider

        # 空态同时隐藏内容、分隔线与占位。
        if not self._enabled:
            holder.setVisible(False)
            card.hide()
            divider.hide()
            return

        # 恢复占位后读取宽度；后续布局事件会补齐首次未收敛的几何。
        holder.setVisible(True)
        seat_w = holder.width()
        if seat_w <= 0:
            return
        scr = self._scroll_area
        if scr is None:
            return
        tl = holder.mapTo(self._owner, QPoint(0, 0))
        natural = tl.y()

        # 卡片外沿 x/宽（编辑区外扩一圈）；分隔线用卡内容 x/宽
        pane = holder.parentWidget()
        if pane is not None:
            ctl = pane.mapTo(self._owner, QPoint(0, 0))
            card_x, card_w = ctl.x(), pane.width()
        else:
            card_x, card_w = tl.x(), seat_w

        card_h = self._height_for(card_w - 2)  # 左右边框共 2px，据此算折行高度
        total_h = card_h + 1  # 分隔线 1px + 编辑区
        outer_margins = (
            pane.layout().contentsMargins() if pane and pane.layout() else None
        )
        margins = card.layout().contentsMargins()
        top_edge = self._edge == "top"
        outer = (
            (outer_margins.top() if top_edge else outer_margins.bottom())
            if outer_margins
            else 0
        )
        shared = min(margins.top() if top_edge else margins.bottom(), outer)
        holder.setFixedHeight(total_h - shared)
        if top_edge:
            natural -= shared

        viewport_top = scr.verticalScrollBar().value()
        pinned_top = (
            viewport_top
            if top_edge
            else viewport_top + scr.viewport().height() - total_h
        )
        pinned = natural < pinned_top if top_edge else natural > pinned_top
        mode = "pin" if pinned else "seat"
        boundary = pinned_top + total_h if top_edge else pinned_top
        corner = self._corner_for(boundary) if pinned else "square"
        self._set_appearance(mode, corner)
        show_divider = not (pinned and corner == "round")
        section_top = pinned_top if pinned else natural
        card_y = section_top if top_edge or not show_divider else section_top + 1
        use_h = total_h if not show_divider else card_h
        card.setGeometry(card_x, card_y, card_w, use_h)
        if show_divider:
            divider_y = card_y + card_h if top_edge else card_y - 1
            divider.setGeometry(tl.x(), divider_y, seat_w, 1)
            divider.show()
        else:
            divider.hide()
        card.show()
        self._restack()

    def _restack(self) -> None:
        """冻结区覆盖原位区；同时冻结时词池在上，层级不受回调顺序影响。"""
        sections = [
            child
            for child in self._owner.children()
            if isinstance(child, FrozenSection) and not child.card.isHidden()
        ]
        for section in sorted(
            sections,
            key=lambda section: (
                section.card.property("state") == "pin",
                section._edge == "bottom",
            ),
        ):
            section.card.raise_()
            if not section._divider.isHidden():
                section._divider.raise_()

    def _corner_for(self, y: int) -> str:
        """判定钉住态顶部 y 落在卡片内（square）还是卡片间空白（round）

        卡片区间取开区间 (top, top+height)：y 严格落在卡片内部才算 square；正好压在
        卡片顶端/底端边框上（含顶端重叠）视为卡片间边界，返回 round。
        """
        for pane in self._panes:
            top = pane.mapTo(self._owner, QPoint(0, 0)).y()
            if top < y < top + pane.height():
                return "square"
        return "round"

    def _set_appearance(self, mode: str, corner: str) -> None:
        """动态属性变化后统一刷新 QSS。"""
        card = self.card
        if card.property("state") == mode and card.property("corner") == corner:
            return
        card.setProperty("state", mode)
        card.setProperty("corner", corner)
        card.style().unpolish(card)
        card.style().polish(card)

    def _height_for(self, width: int) -> int:
        """按给定宽度计算内容及内边距高度。"""
        card = self.card
        lay = card.layout()
        h = lay.heightForWidth(width) if lay is not None else -1
        if h < 0:
            h = card.sizeHint().height()
        return max(1, h)

    def eventFilter(self, obj, event) -> bool:
        if event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.Move,
            QEvent.Type.LayoutRequest,
        ):
            self._layout_timer.start()
        return super().eventFilter(obj, event)
