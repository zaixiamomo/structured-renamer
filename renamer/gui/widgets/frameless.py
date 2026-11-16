"""无边框窗口基类：窗口 chrome（自由缩放 + 跨 DPI 等比缩放）"""

from weakref import WeakSet

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication, QScreen
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

__all__ = ["FramelessWindow"]


class FramelessWindow(QMainWindow):
    """无边框主窗口基类（窗口 chrome 只此一处，不含业务）"""

    # 可拖拽缩放的边缘宽度（逻辑像素）
    _RESIZE_MARGIN = 8
    # 基准逻辑尺寸（逻辑像素）：固定逻辑尺寸交给 Qt 高 DPI 缩放，不同 DPI 屏物理面积一致
    _BASE_LOGICAL = (960, 540)
    # 最小逻辑尺寸（物理面积一致的缩放下限）
    _MIN_LOGICAL = (960, 540)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        # 圆角无边框窗口：背景透明（圆角缝隙透出桌面），objectName 供 QSS 覆盖底色
        self.setObjectName("mainWindow")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # 固定逻辑尺寸启动（showEvent 设最小尺寸）；Qt 高 DPI 缩放负责物理映射
        self.resize(*self._BASE_LOGICAL)
        self._init_dpi_state()

    def _init_dpi_state(self) -> None:
        """跨 DPI / 分辨率屏幕尺寸自适应的状态初始化"""
        self._base_size = self.size()
        self._fit_scheduled = False
        self._screen_hooked = False
        self._dragging = False
        self._drag_go = (
            QPoint()
        )  # 拖拽时"光标 − 窗口左上角"的固定抓取偏移（原生拖拽期间 OS 保持）
        # 自由缩放：边缘/角落悬停显示缩放光标、按下走系统原生缩放（startSystemResize）
        self._cursor_active = False  # 缩放 override cursor 是否已入栈
        self._cursor_shape = None  # 当前 override 光标的形状
        # 已安装事件过滤器的控件（弱引用，随控件销毁自动剔除），只处理新控件
        self._filtered: WeakSet = WeakSet()

    # 自由缩放（无边框窗口边缘/角落拖拽）
    def _install_resize_filter(self) -> None:
        """在窗口及子控件上安装事件过滤器：边缘悬停切缩放光标、按下走系统原生缩放"""
        for w in [self, *self.findChildren(QWidget)]:
            if w in self._filtered:
                continue
            self._filtered.add(w)
            w.installEventFilter(self)
            w.setMouseTracking(True)

    def eventFilter(self, obj, event) -> bool:
        et = event.type()
        if et == QEvent.Type.MouseMove:
            self._update_resize_cursor()
        elif et == QEvent.Type.Leave:
            self._release_resize_cursor()
        elif et == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                edges = self._edge_at_cursor()
                if edges:
                    handle = self.windowHandle()
                    if handle is not None:
                        # 原生缩放循环：平滑、跨 DPI 正确，经 WM_GETMINMAXINFO 遵守当前最小尺寸
                        handle.startSystemResize(edges)
                    self._update_resize_cursor()  # 松手后按光标新位置重估（仍在边缘则保留 override）
                    return True  # 消费掉本次按下，避免顶栏拖动 / 子控件误触发
                # 非边缘按下：交给子类（抽屉 splitter 手柄进入拖拽等）
                self._on_left_press_inside(obj, event)
        elif (
            et == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self._on_left_release(obj, event)
        return False

    def _edge_at_cursor(self) -> Qt.Edges:
        """光标在窗口坐标系下命中的可缩放边缘/角（空 = 不在边缘）"""
        m = self._RESIZE_MARGIN
        r = self.rect()
        pos = self.mapFromGlobal(QCursor.pos())
        edges = Qt.Edges()
        if pos.x() <= r.left() + m:
            edges |= Qt.Edge.LeftEdge
        elif pos.x() >= r.right() - m:
            edges |= Qt.Edge.RightEdge
        if pos.y() <= r.top() + m:
            edges |= Qt.Edge.TopEdge
        elif pos.y() >= r.bottom() - m:
            edges |= Qt.Edge.BottomEdge
        return edges

    @staticmethod
    def _resize_cursor_for(edges: Qt.Edges) -> Qt.CursorShape:
        """按命中边缘返回对应系统缩放光标（斜向两两一组）"""
        if edges == (Qt.Edge.LeftEdge | Qt.Edge.TopEdge) or edges == (
            Qt.Edge.RightEdge | Qt.Edge.BottomEdge
        ):
            return Qt.CursorShape.SizeFDiagCursor
        if edges == (Qt.Edge.RightEdge | Qt.Edge.TopEdge) or edges == (
            Qt.Edge.LeftEdge | Qt.Edge.BottomEdge
        ):
            return Qt.CursorShape.SizeBDiagCursor
        if edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge):
            return Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.SizeVerCursor

    def _update_resize_cursor(self) -> None:
        """悬停窗口边缘（或子类钩子指定的额外区域）时强制显示缩放光标；离开恢复"""
        if self._preempts_resize_cursor():
            self._release_resize_cursor()
            return
        edges = self._edge_at_cursor()
        if edges:
            self._set_cursor(self._resize_cursor_for(edges))
            return
        extra = self._extra_cursor_shape()
        if extra is not None:
            self._set_cursor(extra)
            return
        self._release_resize_cursor()

    def _set_cursor(self, shape: Qt.CursorShape) -> None:
        """入栈 / 就地切换缩放 override cursor（主窗口拖动模式）"""
        if self._cursor_active:
            if shape != self._cursor_shape:
                QApplication.changeOverrideCursor(QCursor(shape))
                self._cursor_shape = shape
        else:
            QApplication.setOverrideCursor(QCursor(shape))
            self._cursor_active = True
            self._cursor_shape = shape

    def _release_resize_cursor(self) -> None:
        """弹出缩放 override cursor（若在栈上）"""
        if self._cursor_active:
            QApplication.restoreOverrideCursor()
            self._cursor_active = False
            self._cursor_shape = None

    # 子类钩子
    def _preempts_resize_cursor(self) -> bool:
        """子控件自带光标语义是否应压过缩放光标（子类覆写；True = 不接管缩放）"""
        return False

    def _extra_cursor_shape(self) -> Qt.CursorShape | None:
        """非窗口边缘时应显示的额外缩放光标（子类覆写，如抽屉手柄横向缩放）"""
        return None

    def _on_left_press_inside(self, obj, event) -> None:
        """非窗口边缘的左键按下（子类覆写）"""

    def _on_left_release(self, obj, event) -> None:
        """左键松开（子类覆写）"""

    # 跨屏幕尺寸自适应（无边框窗口跨 DPI 缩放）
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._screen_hooked:
            handle = self.windowHandle()
            if handle is not None:
                handle.screenChanged.connect(self._on_screen_changed)
                self._screen_hooked = True
        # 物理面积一致：固定逻辑尺寸，Qt 高 DPI 缩放把逻辑像素映射为物理像素
        self.setMinimumSize(*self._MIN_LOGICAL)
        self.resize(*self._BASE_LOGICAL)
        self._snapshot_base()
        self._schedule_fit()

    def event(self, event) -> bool:
        result = super().event(event)
        if event.type() == QEvent.Type.ScreenChangeInternal:
            # Qt 完成 DPI 重排后再修正：拖拽中即时修正，非拖拽延迟对齐
            if self._dragging:
                self._fit_to_screen()
            else:
                self._schedule_fit()
        return result

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        # 拖拽中每次移动即时重估目标屏幕并缩放，避免跨屏瞬间"先放大再恢复"的单帧闪烁
        if self._dragging:
            self._fit_to_screen()

    def _screen_for_center(self) -> QScreen | None:
        """目标屏幕 = 窗口中心点所在屏幕"""
        ref = self._base_size
        w = ref.width() if ref is not None and ref.width() > 0 else self.width()
        h = ref.height() if ref is not None and ref.height() > 0 else self.height()
        center = self.frameGeometry().topLeft() + QPoint(w // 2, h // 2)
        return QGuiApplication.screenAt(center)

    def _screen_for_drag(self) -> QScreen | None:
        """拖拽中的目标屏幕：用冻结基准与抓取偏移反推虚拟中心"""
        ref = self._base_size
        if ref is None or ref.width() <= 0 or ref.height() <= 0:
            return self._screen_for_center()
        cursor = QCursor.pos()
        cx = cursor.x() - self._drag_go.x() + ref.width() // 2
        cy = cursor.y() - self._drag_go.y() + ref.height() // 2
        return QGuiApplication.screenAt(QPoint(cx, cy))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._dragging:
            # 拖拽中 Qt 跨屏会按 DPI 擅自 resize，这里同步把尺寸拉回目标值
            self._fit_to_screen()
            return
        # 全屏/最大化不记录缩放基准：还原时回到全屏前的逻辑尺寸
        if self.isFullScreen() or self.isMaximized():
            return
        # 待重排期间的 resize 是跨屏伪影，不更新基准；其余仅当新尺寸落在当前屏幕内才记录
        if self._fit_scheduled:
            return
        screen = self.screen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        size = event.size()
        if size.width() <= avail.width() and size.height() <= avail.height():
            self._base_size = size

    def _on_drag_started(self) -> None:
        self._dragging = True
        # 记录"光标 − 窗口左上角"的固定抓取偏移（原生拖拽期间 OS 保持它不变），再快照基准
        self._drag_go = QCursor.pos() - self.frameGeometry().topLeft()
        self._snapshot_base()

    # 全屏（顶栏双击切换）
    def toggle_fullscreen(self) -> None:
        """全屏与还原切换（还原回全屏前的正常几何）"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _on_drag_finished(self) -> None:
        self._dragging = False
        self._fit_to_screen()  # 同步收尾到目标比例并刷新基准
        self._nudge_cursor_inside()

    def _nudge_cursor_inside(self) -> None:
        """松手收尾：光标落在窗口外时平移窗口让光标回到窗口边缘内侧"""
        cursor = QCursor.pos()
        fg = self.frameGeometry()
        if fg.contains(cursor):
            return
        x = max(fg.left(), min(fg.right(), cursor.x()))
        y = max(fg.top(), min(fg.bottom(), cursor.y()))
        self.move(fg.x() + (x - cursor.x()), fg.y() + (y - cursor.y()))

    # 最小/默认尺寸：固定逻辑尺寸（物理面积一致）
    def _apply_screen_minimum(self, _screen) -> None:
        """最小尺寸固定为逻辑下限（物理面积一致：不随屏幕 / DPI 变化）"""
        if (self._MIN_LOGICAL[0], self._MIN_LOGICAL[1]) != (
            self.minimumWidth(),
            self.minimumHeight(),
        ):
            self.setMinimumSize(*self._MIN_LOGICAL)

    def _snapshot_base(self) -> None:
        """记录参考基准（当前逻辑尺寸，拖拽期间保持冻结）"""
        screen = self._screen_for_center()
        if screen is not None:
            self._base_size = self.size()

    def _on_screen_changed(self, screen) -> None:
        """窗口移动到新屏幕（分辨率 / DPI 不同）时重新计算几何"""
        if screen is None:
            return
        if self._dragging:
            self._fit_to_screen()
        else:
            self._schedule_fit()

    def _schedule_fit(self) -> None:
        """延迟到 Qt 完成 DPI 事件后再修正几何（否则会被后续放大覆盖）"""
        if self._fit_scheduled:
            return
        self._fit_scheduled = True
        QTimer.singleShot(0, self._fit_to_screen)

    def _fit_to_screen(self) -> None:
        """跨屏收口：保持冻结逻辑尺寸，钳制到目标屏幕可用区"""
        self._fit_scheduled = False
        if self.isMaximized() or self.isFullScreen():
            return
        screen = (
            self._screen_for_drag() if self._dragging else self._screen_for_center()
        )
        if screen is None:
            return
        self._apply_screen_minimum(screen)
        avail = screen.availableGeometry()
        base = self._base_size
        # 物理面积一致：保持冻结逻辑尺寸，只在目标屏可用区更小时钳制到可用区
        w = min(base.width(), avail.width())
        h = min(base.height(), avail.height())
        w = max(self.minimumWidth(), w)
        h = max(self.minimumHeight(), h)
        if (w, h) != (self.width(), self.height()):
            # 拖拽中只改尺寸（左上角不动），光标出窗由松手收尾处理
            self.resize(w, h)
        if not self._dragging:
            self._snapshot_base()
