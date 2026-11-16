"""顶栏：库管理与操作按钮、窗口控制，可拖动移动无边框窗口"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QMenu,
    QPushButton,
    QWidget,
    QWidgetAction,
)

from ..state.session_store import SessionStore
from ..widgets.center_guide import DebugCenterGuide
from ..widgets.optical_label import OpticalLabel

__all__ = ["TopBar"]


class TopBar(QWidget):
    """顶部工具栏"""

    minimize_requested = Signal()
    close_requested = Signal()
    theme_toggle_requested = Signal()
    clear_requested = Signal()
    new_template_requested = Signal()
    new_rule_requested = Signal()
    preview_requested = Signal()
    apply_requested = Signal()
    undo_requested = Signal()
    import_requested = Signal()
    template_reopen_requested = Signal(str)
    rule_reopen_requested = Signal(str)
    # 无边框拖拽开始 / 结束（主窗口据此快照缩放基准 / 重排）
    drag_started = Signal()
    drag_finished = Signal()
    # 顶栏双击切换全屏 / 还原（Windows 标题栏双击惯例）
    fullscreen_requested = Signal()

    def __init__(self, parent=None, *, session: SessionStore):
        super().__init__(parent)
        self._session = session
        self.setObjectName("topbar")
        # 带 border-radius 的 QSS 背景要求显式 WA_StyledBackground，否则普通 QWidget
        # 不绘制底色（窗口透明时直接透出桌面）
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # 规则勾选状态（name 到 bool 映射），跨下拉重建保留，默认勾选
        self._rule_checked: dict[str, bool] = {}
        self._build()
        self._center_guide = DebugCenterGuide(self)
        self._session.changed.connect(self._rebuild_library_menus)
        self._rebuild_library_menus()

    # 构造
    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(6)

        dot = QPushButton()
        dot.setObjectName("brandDot")
        dot.setFixedSize(9, 9)
        dot.setCursor(Qt.CursorShape.PointingHandCursor)
        dot.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        dot.setToolTip("切换主题：蓝（冷）→ 橙（暖）→ 调试（高对比布局）→ …")
        dot.clicked.connect(self.theme_toggle_requested)
        layout.addWidget(dot)

        brand = OpticalLabel("structured-renamer")
        brand.setProperty("role", "brand")
        layout.addWidget(brand)
        layout.addSpacing(8)

        self._btn_import = self._tb_btn("导入", "tb", "导入一个或多个文件夹")
        self._btn_import.clicked.connect(self.import_requested)
        layout.addWidget(self._btn_import)

        self._tpl_btn = self._tb_btn("模板", "tb", "查看/重开已存模板")
        self._tpl_menu = QMenu(self._tpl_btn)
        self._tpl_btn.setMenu(self._tpl_menu)
        layout.addWidget(self._tpl_btn)

        self._rule_btn = self._tb_btn(
            "规则", "tb", "勾选参与预览/执行的规则，点名字重开编辑"
        )
        self._rule_menu = QMenu(self._rule_btn)
        self._rule_btn.setMenu(self._rule_menu)
        layout.addWidget(self._rule_btn)

        layout.addStretch(1)

        self._btn_clear = self._tb_btn("清空", "tb", "清除执行结果状态色")
        self._btn_clear.clicked.connect(self.clear_requested)
        layout.addWidget(self._btn_clear)
        layout.addWidget(self._sep())

        self._btn_new_template = self._tb_btn("新建模板", "tb", "新建模板窗口")
        self._btn_new_template.clicked.connect(self.new_template_requested)
        layout.addWidget(self._btn_new_template)
        self._btn_new_rule = self._tb_btn("新建规则", "tb", "新建规则窗口")
        self._btn_new_rule.clicked.connect(self.new_rule_requested)
        layout.addWidget(self._btn_new_rule)
        layout.addWidget(self._sep())

        self._btn_preview = self._tb_btn(
            "预览", "tb", "试运行：预览改名结果（不真实改名）"
        )
        self._btn_preview.clicked.connect(self.preview_requested)
        layout.addWidget(self._btn_preview)
        self._btn_apply = self._tb_btn(
            "执行", "tb-primary", "真实执行改名（写撤销日志）"
        )
        self._btn_apply.clicked.connect(self.apply_requested)
        layout.addWidget(self._btn_apply)
        self._btn_undo = self._tb_btn("撤回", "tb", "撤销上次改名")
        self._btn_undo.clicked.connect(self.undo_requested)
        layout.addWidget(self._btn_undo)
        layout.addWidget(self._sep())

        self._btn_min = self._winctl("—", "winctl", "最小化")
        self._btn_close = self._winctl("✕", "winctl-close", "关闭")

        self._btn_min.clicked.connect(self.minimize_requested)
        self._btn_close.clicked.connect(self.close_requested)

        layout.addWidget(self._btn_min)
        layout.addWidget(self._btn_close)

    # 库下拉
    def _rebuild_library_menus(self) -> None:
        """按会话库重建「模板 / 规则」两个下拉（库变化时调用）"""
        self._tpl_menu.clear()
        for name in self._session.template_names():
            act = self._tpl_menu.addAction(name)
            act.triggered.connect(
                lambda _c=False, n=name: self.template_reopen_requested.emit(n)
            )

        self._rule_menu.clear()
        for name in self._session.rule_names():
            self._rule_checked.setdefault(name, True)  # 默认勾选，保留已有状态
            wa = QWidgetAction(self._rule_menu)
            row = QWidget()
            hl = QHBoxLayout(row)
            hl.setContentsMargins(10, 3, 8, 3)
            hl.setSpacing(6)
            chk = QCheckBox()
            chk.setChecked(self._rule_checked[name])
            chk.toggled.connect(
                lambda on, n=name: self._rule_checked.__setitem__(n, on)
            )
            hl.addWidget(chk)
            edit = QPushButton(name)
            edit.setFlat(True)
            edit.setCursor(Qt.CursorShape.PointingHandCursor)
            edit.setToolTip("点击重新打开编辑")
            edit.clicked.connect(
                lambda _c=False, n=name: self.rule_reopen_requested.emit(n)
            )
            hl.addWidget(edit, 1)
            wa.setDefaultWidget(row)
            self._rule_menu.addAction(wa)

    def checked_rule_names(self) -> list[str]:
        """当前勾选的规则名（参与预览/执行）"""
        return [
            n for n in self._session.rule_names() if self._rule_checked.get(n, True)
        ]

    @staticmethod
    def _winctl(text: str, role: str, tip: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setProperty("role", role)
        btn.setToolTip(tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(36, 28)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return btn

    @staticmethod
    def _tb_btn(text: str, role: str, tip: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setProperty("role", role)
        btn.setToolTip(tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(28)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return btn

    @staticmethod
    def _sep() -> QWidget:
        sep = QWidget()
        sep.setObjectName("tbSep")
        sep.setFixedSize(1, 18)
        return sep

    # 无边框拖动
    def mouseDoubleClickEvent(self, event) -> None:
        """左键双击顶栏空白区切换全屏 / 还原（Windows 标题栏双击惯例）"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.fullscreen_requested.emit()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            # 交给系统原生 startSystemMove 拖动循环：消除手动 move 与异步 DPI
            # 变更赛跑造成的缩放闪烁；期间窗口仍收到 moveEvent/screenChanged 供等比缩放
            self.drag_started.emit()
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemMove()
            self.drag_finished.emit()
            event.accept()
        else:
            super().mousePressEvent(event)
