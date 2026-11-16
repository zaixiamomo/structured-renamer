"""窗口缩略列（发丝线接缝）：胶囊跨骑在树与窗口分界线上"""

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..state.window import Window, WindowManager
from ..theme import T, ThemeManager

__all__ = ["ThumbsColumn"]

# 胶囊几何：外轮廓 16px（选中蓝圈外径），未选中灰圆 13px，选中时内缩到 10px 外露蓝圈
STRIP_W = int(T("size.thumbs.w"))
BLOCK = 16  # 外轮廓：选中蓝圈外径
GRAY = 13  # 未选中模板圆直径（> INNER，纯灰有存在感但不抢眼）
GRAY_RULE = 12  # 未选中规则方形边长：视觉上比同径圆「胀大」，按等面积缩小
INNER = 10  # 选中时内缩灰圆直径
RING = (BLOCK - INNER) // 2  # 选中蓝圈环宽（3px）
RULE_RADIUS = 5  # 规则胶囊外轮廓圆角（选中态，比方形更圆润）
RULE_RADIUS_IDLE = 3  # 规则胶囊未选中圆角（更方，与圆形拉开差异）
HAIRLINE_LEFT = STRIP_W // 2  # 发丝线 x（左半树色 + 1px 线 + 右半抽屉色）
CAPSULE_GAP = 9
CAPSULE_PAD_TOP = 14


class ThumbBlock(QWidget):
    """单个窗口缩略胶囊"""

    clicked = Signal()

    def __init__(self, win: Window, manager: WindowManager, parent=None):
        super().__init__(parent)
        self._win = win
        self._manager = manager
        self._hovered = False
        self.setFixedSize(BLOCK, BLOCK)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # 鼠标跟踪：让 MouseMove 到达 frameless 事件过滤器，释放粘在胶囊上的缩放光标
        self.setMouseTracking(True)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        footprint = self.rect()  # 块控件 16px
        active = self._manager.is_active(self._win)
        is_rule = self._win.type == "rule"
        color = QColor(self._manager.identity_color(self._win))

        if active:
            # 前端：蓝圈铺满外轮廓，灰圆收小到 10px；内圆角 = 外圆角 − 环宽，蓝环厚度均匀
            inner = footprint.adjusted(RING, RING, -RING, -RING)
            inner_radius = max(1, RULE_RADIUS - RING)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(T("color.accent")))
            self._draw_shape(painter, footprint, is_rule)
            color.setAlphaF(1.0)
            painter.setBrush(color)
            self._draw_shape(painter, inner, is_rule, inner_radius)
            # 白内描边：内圆在蓝圈上的定义感
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(255, 255, 255, 140), 1))
            self._draw_shape(painter, inner, is_rule, inner_radius)
            return

        # 后台/缩略/hover：实心浅灰圆（与白色混合的不透明色，不用 alpha，避免透出发丝线分界线）
        g = GRAY_RULE if is_rule else GRAY  # 规则方形按等面积缩小，避免显得比圆大
        off = (BLOCK - g) // 2
        gray_rect = QRect(off, off, g, g)
        fill = self._mix(color, 70 if not self._hovered else 40)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        self._draw_shape(painter, gray_rect, is_rule, RULE_RADIUS_IDLE)
        # 内描边用发丝线色（border.strong）：浅底上有明确边界感
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(T("color.border.strong")), 1))
        self._draw_shape(painter, gray_rect, is_rule, RULE_RADIUS_IDLE)

    @staticmethod
    def _mix(color: QColor, white_pct: float) -> QColor:
        """与白色按百分比混合成不透明色（white_pct = 白比例 0-100）"""
        return QColor(
            round(color.red() + (255 - color.red()) * white_pct / 100),
            round(color.green() + (255 - color.green()) * white_pct / 100),
            round(color.blue() + (255 - color.blue()) * white_pct / 100),
        )

    @staticmethod
    def _draw_shape(painter, rect, is_rule: bool, radius: int = RULE_RADIUS) -> None:
        """按类型绘制形状：模板 = 圆，规则 = 圆角方（radius 可调，内圈随环宽收缩）"""
        if is_rule:
            painter.drawRoundedRect(rect, radius, radius)
        else:
            painter.drawEllipse(rect)


class ThumbsColumn(QWidget):
    """缩略列容器：按窗口状态渲染胶囊，自身即抽屉拉伸触发边"""

    # 抽屉拉伸拖拽信号（负载 = 光标全局 x，Drawer 据此换算抽屉宽）
    resize_started = Signal(int)
    resize_moved = Signal(int)
    resize_finished = Signal()

    def __init__(self, manager: WindowManager, parent=None):
        super().__init__(parent)
        self.setObjectName("thumbsColumn")
        self._manager = manager
        self._blocks: dict[int, ThumbBlock] = {}
        self._layout = QVBoxLayout(self)
        side_margin = (STRIP_W - BLOCK) // 2
        self._layout.setContentsMargins(
            side_margin, CAPSULE_PAD_TOP, side_margin, CAPSULE_PAD_TOP
        )
        self._layout.setSpacing(CAPSULE_GAP)
        self._layout.addStretch(1)
        self.setFixedWidth(0)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        manager.changed.connect(self._sync)
        ThemeManager.instance().theme_changed.connect(self._repaint)
        self._sync()

    # 拉伸拖拽（接缝自身 = 触发边）
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.resize_started.emit(round(event.globalPosition().x()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.resize_moved.emit(round(event.globalPosition().x()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.resize_finished.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _on_block_clicked(self, win: Window) -> None:
        if self._manager.is_active(win):
            self._manager.collapse(win.id)
        else:
            self._manager.switch_to(win.id)

    def cursor_over_capsule(self, global_pos) -> bool:
        """全局坐标是否落在某颗胶囊上（主窗口据此不放横向缩放光标）"""
        local = self.mapFromGlobal(global_pos)
        for block in self._blocks.values():
            if block.geometry().contains(local):
                return True
        return False

    def _sync(self) -> None:
        """增量同步：结构变化只增删块，已有块状态变化只重绘，不销毁重建"""
        wins = self._manager.windows
        alive = {w.id for w in wins}
        for wid in [w for w in self._blocks if w not in alive]:
            block = self._blocks.pop(wid)
            block.setParent(None)
            block.deleteLater()
        for win in wins:
            if win.id not in self._blocks:
                block = ThumbBlock(win, self._manager, self)
                block.clicked.connect(lambda w=win: self._on_block_clicked(w))
                self._layout.insertWidget(self._layout.count() - 1, block)
                self._blocks[win.id] = block
            else:
                self._blocks[win.id].update()
        self.setFixedWidth(STRIP_W if wins else 0)
        # 发丝线接缝为固定静态背景，容器整体重绘即可
        self.update()

    def _repaint(self) -> None:
        """主题切换只触发重绘，不动结构"""
        for block in self._blocks.values():
            block.update()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        w, h = self.width(), self.height()
        if w <= 0:
            return
        # 两列分色：左半归文件树、右半归侧边窗口，中间 1px 发丝线即分界线
        painter.fillRect(QRect(0, 0, HAIRLINE_LEFT, h), QColor(T("color.bg.surface2")))
        painter.fillRect(
            QRect(HAIRLINE_LEFT, 0, w - HAIRLINE_LEFT, h), QColor(T("color.bg.surface"))
        )
        # 发丝线：关抗锯齿 + 整数坐标，1px 细线清晰
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(QPen(QColor(T("color.border.strong")), 1))
        painter.drawLine(HAIRLINE_LEFT, 0, HAIRLINE_LEFT, h)
        # Debug：左右两半填充色与相邻的树/面板一致，光靠颜色分不清该列归属；
        # 用虚线外框把整列自身轮廓画出来（中间的白色发丝线即两半分界）
        if ThemeManager.instance().series == "debug":
            pen = QPen(QColor("#6a1b9a"), 1)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(0, 0, w - 1, h - 1)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
