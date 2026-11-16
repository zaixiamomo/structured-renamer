"""主窗口：无边框三分区骨架，组装文件树与侧边抽屉并接线右键菜单、业务"""

from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from ..batch import BatchCoordinator
from ..state.window import WindowManager
from ..theme import T, ThemeManager
from ..widgets.drawer import Drawer
from ..widgets.frameless import FramelessWindow
from .bottombar import BottomBar
from .rule_panel import RulePanel
from .template_panel import TemplatePanel
from .topbar import TopBar


class MainWindow(FramelessWindow):
    """三分区主窗口（无边框）"""

    def __init__(self, parent=None, *, executor, capability_runner, authoring, session):
        super().__init__(parent)
        # 执行接缝（app.py 装配注入真实实现，无 mock 回退）
        self._session = session
        self._capability_runner = capability_runner
        self._authoring = authoring
        self.setWindowTitle("structured-renamer")
        self._manager = WindowManager()
        self._manager.window_opened.connect(self._on_window_opened)
        # 待载入的库条目（"template"/"rule", name, 对象），重开编辑时由 _on_window_opened 消费
        self._pending_load = None
        self._build()
        self._batch = BatchCoordinator(executor, self._collect_files, self)
        self._batch.files_changed.connect(self._refresh_files)
        self._batch.message_changed.connect(self._bottombar.set_message)
        self._batch.run_info_changed.connect(self._bottombar.set_run_info)
        # 底栏左侧初始化：文件树结构启动后不再变化，总文件数只填一次，
        # 已选数随复选框变化更新（_on_check_count_changed）
        self._on_check_count_changed(0)
        self._install_resize_filter()
        # 缩略列胶囊在窗口打开后才动态创建，初次安装过滤器时尚未存在；
        # 每次窗口结构变化后重跑幂等安装，否则缩放光标会粘在胶囊上不释放
        self._manager.changed.connect(self._install_resize_filter)

    def _build(self) -> None:
        # QFrame 按 QSS 边框自动内缩内容，避免子控件覆盖窗口轮廓。
        central = QFrame()
        central.setObjectName("mainRoot")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._topbar = TopBar(session=self._session)
        self._topbar.minimize_requested.connect(self.showMinimized)
        self._topbar.close_requested.connect(self.close)
        self._topbar.theme_toggle_requested.connect(ThemeManager.instance().toggle)
        self._topbar.clear_requested.connect(self._clear_status)
        self._topbar.new_template_requested.connect(
            lambda: self._open_window("template")
        )
        self._topbar.new_rule_requested.connect(lambda: self._open_window("rule"))
        self._topbar.import_requested.connect(self._import_folder)
        self._topbar.template_reopen_requested.connect(self._reopen_template)
        self._topbar.rule_reopen_requested.connect(self._reopen_rule)
        self._topbar.preview_requested.connect(self._on_preview)
        self._topbar.apply_requested.connect(self._on_apply)
        self._topbar.undo_requested.connect(self._undo)
        self._topbar.drag_started.connect(self._on_drag_started)
        self._topbar.drag_finished.connect(self._on_drag_finished)
        self._topbar.fullscreen_requested.connect(self.toggle_fullscreen)
        root.addWidget(self._topbar)

        main = QWidget()
        main.setObjectName("mainArea")
        # QSS 底色需要显式 WA_StyledBackground（普通 QWidget 默认不绘制）
        main.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(main)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        # 文件树（含左侧专属滚动条）
        tree = QWidget()
        tree.setObjectName("treeArea")
        # 抽屉拖拽增宽的兜底下限：文件树不被挤没（QSplitter 拖拽尊重 minimum）
        tree.setMinimumWidth(int(T("size.tree.min.w")))
        self._tree_layout = QHBoxLayout(tree)
        self._tree_layout.setContentsMargins(0, 0, 0, 0)
        self._tree_layout.setSpacing(0)
        self._tree_view = None
        self._tree_scrollbar = None

        # 侧边抽屉（缩略列 + 侧面板 + QSplitter + 动画），与文件树并排
        self._drawer = Drawer(self._manager, tree)
        row.addWidget(self._drawer)

        root.addWidget(main, 1)
        self._bottombar = BottomBar()
        root.addWidget(self._bottombar)

        self.setCentralWidget(central)

    # 文件树根（导入文件夹 / 启动注入）
    def _set_tree(self, root) -> None:
        """设置文件树根；树视图懒创建，已有则替换根并重建"""
        if self._tree_view is None:
            from ..widgets.tree_scrollbar import TreeScrollBar
            from ..widgets.tree_view import TreeView

            self._tree_view = TreeView(root)
            self._tree_scrollbar = TreeScrollBar(self._tree_view)
            self._tree_view.check_count_changed.connect(self._on_check_count_changed)
            self._tree_view.context_menu_requested.connect(self._show_context_menu)
            self._tree_layout.addWidget(self._tree_scrollbar)
            self._tree_layout.addWidget(self._tree_view, 1)
        else:
            self._tree_view.set_root(root)
        self._on_check_count_changed(0)

    def _import_folder(self) -> None:
        """导入一个或多个文件夹并扫描构建文件树（替换当前树）"""
        dialog = QFileDialog(self, "导入文件夹")
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        # 非原生对话框支持多选目录
        for view in dialog.findChildren(QAbstractItemView):
            view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        if dialog.exec() != QFileDialog.DialogCode.Accepted:
            return
        dirs = [Path(p) for p in dialog.selectedFiles()]
        if not dirs:
            return
        from ..scan import scan_dirs

        self._set_tree(scan_dirs(dirs))

    # 文件树事件
    def _on_check_count_changed(self, count: int) -> None:
        """复选框勾选文件数变化，更新底栏总文件数与已选文件数"""

        total = len(self._tree_view.collect_files()) if self._tree_view else 0
        self._bottombar.set_counts(total, count)

    def _show_context_menu(self, node, global_pos: QPoint) -> None:
        menu = QMenu(self)
        # 圆角菜单：QMenu 默认带原生方角背景/阴影，会盖在 QSS 的 border-radius 后面；
        # 设 Frameless + 无阴影 + 半透明背景后，QSS 底色才被圆角裁切（角区透明）
        menu.setWindowFlags(
            menu.windowFlags()
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        if node is not None and self._tree_view.is_selected(node):
            # 右键选中集内文件（单选或批量）：出「新建模板」「新建规则」，
            # 以被右键文件名为示例，与顶栏同一入口 _open_window
            new_template_action = menu.addAction("新建模板")
            new_rule_action = menu.addAction("新建规则")
            chosen = menu.exec(global_pos)
            if chosen is new_template_action:
                self._open_window(
                    "template", str(node.path) if node.path else node.name
                )
            elif chosen is new_rule_action:
                self._open_window("rule", str(node.path) if node.path else node.name)
        else:
            # 空白 / 目录 / 非选中文件：只出树操作
            collapse_action = menu.addAction("折叠全部")
            expand_action = menu.addAction("展开全部")
            chosen = menu.exec(global_pos)
            if chosen is collapse_action:
                self._tree_view.collapse_all()
            elif chosen is expand_action:
                self._tree_view.expand_all()

    # 编辑窗口
    def _open_window(self, type_: str, filename: str | None = None) -> None:
        # 顶栏「新建模板/新建规则」不带 filename，默认空窗；只有文件树右键菜单才
        # 显式传入文件名作为示例（进入编辑即导入该文件）
        self._manager.open(type_, filename)

    def _on_window_opened(self, win) -> None:
        if win.type == "rule":
            panel = RulePanel(
                win,
                manager=self._manager,
                runner=self._capability_runner,
                authoring=self._authoring,
                session=self._session,
            )
        else:
            panel = TemplatePanel(
                win,
                manager=self._manager,
                authoring=self._authoring,
                session=self._session,
            )
        # 消费重开编辑的待载入条目
        if self._pending_load is not None:
            kind, name, payload = self._pending_load
            self._pending_load = None
            if kind == "template" and win.type == "template":
                panel.load_template(name, payload)
            elif kind == "rule" and win.type == "rule":
                panel.load_rule(name, payload)
        self._drawer.side_panel.add_window(win, panel)

    def _reopen_template(self, name: str) -> None:
        tpl = self._session.parse_templates.get(name)
        if tpl is None:
            return
        self._pending_load = ("template", name, tpl)
        self._manager.open("template", title=f"编辑模板：{name}")

    def _reopen_rule(self, name: str) -> None:
        rule = self._session.get_rule(name)
        if rule is None:
            return
        self._pending_load = ("rule", name, rule)
        self._manager.open("rule", title=f"编辑规则：{name}")

    # 无边框窗口钩子（接缝横向缩放光标）
    def _preempts_resize_cursor(self) -> bool:
        """缩略列胶囊在窗口右缘时不被边缘缩放光标接管"""
        if self._drawer.dragging and bool(
            QApplication.mouseButtons() & Qt.MouseButton.LeftButton
        ):
            return False
        handle = self._drawer.drawer_handle()
        if handle is None or not handle.isVisible():
            return False
        over = getattr(handle, "cursor_over_capsule", None)
        return over is not None and over(QCursor.pos())

    def _extra_cursor_shape(self) -> Qt.CursorShape | None:
        """缩略列接缝悬停或拖拽时给出横向缩放光标"""
        dragging = self._drawer.dragging and bool(
            QApplication.mouseButtons() & Qt.MouseButton.LeftButton
        )
        if dragging or self._cursor_over_handle():
            return Qt.CursorShape.SizeHorCursor
        return None

    def _on_left_release(self, obj, event) -> None:
        if self._drawer.dragging:
            self._drawer.dragging = False

    def _cursor_over_handle(self) -> bool:
        """光标是否落在缩略列接缝（非胶囊）上"""
        handle = self._drawer.drawer_handle()
        if handle is None or not handle.isVisible():
            return False
        over_capsule = getattr(handle, "cursor_over_capsule", None)
        if over_capsule is not None and over_capsule(QCursor.pos()):
            return False
        return handle.rect().contains(handle.mapFromGlobal(QCursor.pos()))

    # 预览 / 执行 / 清空 / 撤回（真实接缝，异步回主线程）
    def _on_preview(self) -> None:
        self._start_run(preview=True)

    def _on_apply(self) -> None:
        self._start_run(preview=False)

    def _start_run(self, *, preview: bool) -> None:
        if self._tree_view is None:
            self._bottombar.set_message("先导入文件夹，还没有文件树")
            return
        files = self._tree_view.checked_files()
        if not files:
            self._bottombar.set_message("没有勾选文件，先勾选要改名的文件")
            return
        rule_names = self._topbar.checked_rule_names()
        if not rule_names:
            self._bottombar.set_message(
                "未勾选规则，先在顶部栏「规则」勾选要执行的规则"
            )
            return
        self._batch.run(files, rule_names, preview=preview)

    def _collect_files(self) -> list:
        return self._tree_view.collect_files() if self._tree_view is not None else []

    def _refresh_files(self) -> None:
        if self._tree_view is not None:
            self._tree_view.model_changed.emit()

    def _clear_status(self) -> None:
        if self._tree_view is not None:
            self._batch.clear()

    def _undo(self) -> None:
        self._batch.undo()
