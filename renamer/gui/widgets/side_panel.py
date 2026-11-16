"""侧面板容器：展开挤树 / 空收起 / 全缩略时收起但色块列保留"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..state.window import Window, WindowManager
from ..theme import T
from .inline_edit import InlineEdit
from .panel_scroll import PanelScrollArea
from .panel_stack import PanelStack

if TYPE_CHECKING:
    from ..views.panel_base import EditorPanel

__all__ = ["SidePanel"]


class SidePanel(QWidget):
    """编辑侧面板容器"""

    # 面板显隐切换（True = 有前端窗口、面板展开），MainWindow 据此用 QSplitter
    # setSizes 恢复（展开）或收敛（收起）抽屉宽度
    visibility_changed = Signal(bool)
    # 面板内容所需最小宽变化（词流增删），MainWindow 据此把抽屉加宽到卡片完整
    # 显示所需宽度（若当前抽屉已窄于该值）
    min_width_changed = Signal(int)

    def __init__(self, manager: WindowManager, parent=None):
        super().__init__(parent)
        self.setObjectName("sidePanelArea")
        # QSS 底色需显式 WA_StyledBackground：普通 QWidget 默认不绘制 stylesheet 背景
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._manager = manager
        self._panels: dict[int, EditorPanel] = {}
        self._current_panel: EditorPanel | None = None
        self._visible = False
        # 窗口间共享滚动区；切走存档，切回交给 PanelScrollArea 恢复。
        self._win_scroll: dict[int, int] = {}
        # 当前正显示内容所属窗口 id（None = 空白页），切窗滚动存档/恢复的依据
        self._shown_id: int | None = None
        # 收起态：宽度上界压到 0（保留在 QSplitter 内可协作，不用 setFixedWidth）
        self.setMaximumWidth(0)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._head = self._build_head()
        # 顶栏名称编辑框的「用户已编辑」标志：编辑期间 _sync 不覆盖输入；切换窗口时重置
        self._title_dirty = False
        self._last_synced_win: int | None = None
        root.addWidget(self._head)

        self._stack = PanelStack()
        self._stack.setObjectName("sidePanelStack")
        self._blank = QWidget()
        self._blank.setObjectName("blankPanel")
        self._stack.addWidget(self._blank)
        self._scroll = PanelScrollArea(self._stack)
        root.addWidget(self._scroll, 1)
        self._scroll.verticalScrollBar().rangeChanged.connect(self._sync_divider_inset)
        self._sync_divider_inset()

        manager.changed.connect(self._sync)
        self._sync()

    def add_window(self, win: Window, panel: EditorPanel) -> None:
        """登记面板到侧面板（由 MainWindow 在 window_opened 时调用）"""
        panel.setObjectName("sidePanelPage")
        self._panels[win.id] = panel
        self._stack.addWidget(panel)
        panel.attach_scroll_area(self._scroll)
        # 新页面更宽时收紧宽度下限；词流增删会改变内容宽，也订阅通知
        self.refresh_min_width()
        panel.content_changed.connect(self.refresh_min_width)
        # 内容结构变化（词流/块增删）后延迟重算正文滚动范围，防止陈旧范围残留
        panel.content_changed.connect(self._scroll.refit)
        # 面板内改名（顶栏编辑触发）时同步标题栏
        panel.name_changed.connect(self._on_panel_name_changed)
        # 面板请求编辑名称（模板卡 TOML 点 name）时聚焦标题栏名称编辑框
        panel.name_edit_requested.connect(self._begin_title_edit)

    def _on_panel_name_changed(self) -> None:
        """面板名变化通知：刷新顶栏标题（保持与面板 name 一致）"""
        panel = self.sender()
        if panel is not None and panel is self._current_panel:
            self._sync_title(panel)

    def _begin_title_edit(self) -> None:
        """外部请求编辑当前名称：聚焦标题栏编辑框并全选（模板卡 TOML 点 name）"""
        if self._current_panel is not None:
            self._title.setFocus(Qt.FocusReason.MouseFocusReason)
            self._title.selectAll()

    @property
    def minimum_content_width(self) -> int:
        return self._min_content_w

    def refresh_min_width(self) -> None:
        """宽度下限同时容纳标题栏及所有编辑页。"""
        head_w = self._head.minimumSizeHint().width()
        stack_w = self._stack.minimumSizeHint().width()
        sb_w = self._scroll.verticalScrollBar().sizeHint().width()
        self._min_content_w = max(head_w, stack_w) + sb_w
        if self._visible:
            self.setMinimumWidth(
                max(int(T("size.side_panel.w.min")), self._min_content_w)
            )
        self.min_width_changed.emit(self._min_content_w)

    def _sync_divider_inset(self) -> None:
        """分隔线右侧内缩 = 12px 基础 + 滚动条占宽（滚动条可见时）"""
        extra = 0
        sb = self._scroll.verticalScrollBar()
        if sb.isVisible():
            extra = sb.sizeHint().width()
        self._divider_lay.setContentsMargins(12, 0, 12 + extra, 0)

    def force_live_page(self) -> None:
        """动画抓取快照前，把面板栈切到实况页"""
        win = self._manager.active_window()
        panel = self._panels.get(win.id) if win else None
        if panel is not None:
            self._stack.setCurrentWidget(panel)

    def _prune_closed(self) -> None:
        """移除已关闭窗口的面板页，避免残留死页继续占栈（高度地板与内存）"""
        live = {w.id for w in self._manager.windows}
        for win_id in [i for i in self._panels if i not in live]:
            panel = self._panels.pop(win_id)
            if self._stack.currentWidget() is not panel:
                self._stack.removeWidget(panel)
                panel.deleteLater()
            self._win_scroll.pop(win_id, None)

    def _save_shown_scroll(self) -> None:
        """切窗/收起前，存档当前正显示窗口的正文滚动值"""
        shown = self._shown_id
        if shown is None or shown not in self._panels:
            return
        self._win_scroll[shown] = self._scroll.verticalScrollBar().value()

    def notify_drawer_settled(self) -> None:
        """抽屉动画结束后，让滚动区按最终宽度重新计算内容高度。"""
        self._scroll.refit()

    # 构造
    def _build_head(self) -> QWidget:
        head = QWidget()
        head.setObjectName("sidePanelHead")
        # 同 sidePanelArea：普通 QWidget 需显式 WA_StyledBackground 才绘制 QSS 底色
        head.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        vlay = QVBoxLayout(head)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)

        # 工具栏行：色条 + 标题 + 操作按钮
        toolbar = QWidget()
        lay = QHBoxLayout(toolbar)
        lay.setContentsMargins(12, 10, 12, 9)
        lay.setSpacing(8)

        self._color_bar = QFrame()
        self._color_bar.setObjectName("sidePanelColor")
        self._color_bar.setFrameShape(QFrame.Shape.NoFrame)
        self._color_bar.setFixedSize(3, 22)
        lay.addWidget(self._color_bar)

        # 标题 = 「编辑模板/规则」+ 模板/规则名（灰、下划线、可编辑），顶栏改名即同步到面板
        self._kind = QLabel("编辑模板")
        self._kind.setProperty("role", "side-panel-kind")
        lay.addWidget(self._kind)

        self._title = InlineEdit()
        self._title.setProperty("role", "side-panel-title-edit")
        self._title.setAcceptDrops(False)
        self._title.setCursor(Qt.CursorShape.IBeamCursor)
        # 仅点击聚焦：打开侧边窗口时不自动进入编辑态
        self._title.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._title.textEdited.connect(self._on_title_edited)
        # 编辑结束（回车/失焦）后清除 dirty，让 _sync 可覆盖标题；
        # 空值回显、回车收口等编辑体验由 UnderlineEdit 基类统一负责
        self._title.editingFinished.connect(self._on_title_finished)
        lay.addWidget(self._title)
        # 名称不占满剩余空间（宽度跟随文本），按钮保持右对齐
        lay.addStretch(1)

        self._btn_save = QPushButton("")
        self._btn_save.setProperty("role", "d-btn-primary")
        self._btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_save.clicked.connect(self._on_save)
        lay.addWidget(self._btn_save)

        self._close_btn = QPushButton("✕")
        self._close_btn.setProperty("role", "d-btn")
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.clicked.connect(self._manager.close_active)
        lay.addWidget(self._close_btn)
        vlay.addWidget(toolbar)

        # 分隔线行：左右各留 12px 空白，两侧悬空不贴边；右侧内缩补上滚动条占宽
        self._divider_row = QWidget()
        self._divider_row.setObjectName("sidePanelDividerRow")
        self._divider_lay = QHBoxLayout(self._divider_row)
        self._divider_lay.setContentsMargins(12, 0, 12, 0)
        self._divider_lay.setSpacing(0)
        line = QWidget()
        line.setObjectName("sidePanelDivider")
        line.setFixedHeight(1)
        self._divider_lay.addWidget(line)
        vlay.addWidget(self._divider_row)
        return head

    # 联动
    def _sync(self) -> None:
        win = self._manager.active_window()
        visible = win is not None
        # 显隐切换才调整宽度上限；切换编辑页仍需刷新内容宽度下限。
        toggled = visible != self._visible
        # 切窗/收起先存档当前窗口的滚动位置，再动页面
        self._save_shown_scroll()
        if toggled:
            self._visible = visible
            if visible:
                self.setMaximumWidth(int(T("size.side_panel.w.max")))
                self.refresh_min_width()
            else:
                # min/max 一起压到 0：否则残留的 min 会撑住 minimumSizeHint，抽屉无法收窄
                self.setMaximumWidth(0)
                self.setMinimumWidth(0)
        elif visible:
            # 前台窗口切换：不同面板内容所需宽度不同，显隐没变也要重算下限
            self.refresh_min_width()
        # 显隐信号前先就位头部与正文，快照不带旧/空样式；收起方向先抓实况页快照再切空白页
        if not visible:
            if toggled:
                self.visibility_changed.emit(visible)
            self._stack.setCurrentWidget(self._blank)
            self._shown_id = None
            self._prune_closed()
            return
        win_changed = win.id != self._shown_id
        panel = self._panels.get(win.id)
        if panel is not None:
            self._stack.setCurrentWidget(panel)
        self._current_panel = panel
        self._shown_id = win.id
        self._prune_closed()
        # 切换窗口后重置上一位的编辑 dirty（dirty 只在同窗口编辑期有效）
        if win.id != self._last_synced_win:
            self._last_synced_win = win.id
            self._title_dirty = False
        kind = "编辑规则" if win.type == "rule" else "编辑模板"
        self._kind.setText(kind)
        self._sync_title(panel)
        self._btn_save.setText("保存")
        # 同页内容变化保留当前位置，换页才恢复存档。
        if win_changed and panel is not None:
            self._scroll.restore_position(self._win_scroll.get(win.id, 0))
        if toggled:
            self.visibility_changed.emit(visible)

    def _sync_title(self, panel) -> None:
        """标题栏与面板当前名对齐；用户正在编辑（dirty）且持有焦点时不覆盖"""
        name = panel.name if panel is not None else ""
        if (
            not (self._title_dirty and self._title.hasFocus())
            and self._title.text() != name
        ):
            self._title.setText(name)
            self._title_dirty = False
            # 非编辑态下光标归 0：名称超长时左侧完整显示、右侧隐藏
            self._title.setCursorPosition(0)

    def _on_title_edited(self, text: str) -> None:
        """顶栏名称编辑时标记 dirty 并同步到当前面板（模板/规则重命名）"""
        self._title_dirty = True
        panel = self._current_panel
        if panel is not None:
            panel.set_name(text)

    def _on_title_finished(self) -> None:
        """标题编辑结束（回车/失焦）：空值回显已由 UnderlineEdit 处理，这里只清 dirty"""
        self._title_dirty = False

    def _on_save(self) -> None:
        """保存：面板自行校验并登记；成功才关闭侧边窗口"""
        panel = self._current_panel
        if panel is not None and panel.save():
            self._manager.close_active()
