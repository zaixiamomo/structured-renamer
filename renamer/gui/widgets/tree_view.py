"""文件树：嵌套目录折叠/展开 + 三态复选框 + 行选中 + 状态行底色"""

from bisect import bisect_right

from PySide6.QtCore import QMimeData, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QPainter
from PySide6.QtWidgets import QAbstractScrollArea, QApplication, QFrame

from renamer.app import Status

from ..state.files import TreeNode
from ..state.status_style import STATUS_STYLE
from ..theme import T, ThemeManager
from .tree_paint import drag_pixmap, ghost_name, hit_area, paint_row

__all__ = ["TreeView"]

# 拖放文件节点的自定义 MIME 类型（模板面板据此识别「文件树到模板」的拖入文件名）
MIME_FILE = "application/x-structured-renamer-file"


class TreeView(QAbstractScrollArea):
    """自绘文件树"""

    # 单选文件行（参数为对应 TreeNode）
    file_selected = Signal(object)
    # 复选框勾选文件数变化（参数为勾选文件总数，目录行不计入）
    check_count_changed = Signal(int)
    # 树区域右键（参数为命中的 TreeNode 或 None，与全局坐标 QPoint）
    context_menu_requested = Signal(object, object)
    # 树结构 / 状态变化（小地图缓存、自绘刷新据此重建）
    model_changed = Signal()

    def __init__(self, root: TreeNode, parent=None):
        super().__init__(parent)
        self.setObjectName("treeView")
        self._root = root
        self._rows: list[tuple[TreeNode, int]] = []
        self._anchor: TreeNode | None = None  # Shift 批量选区的锚点文件行
        self._multi: set[TreeNode] = set()  # 当前选中文件集（单选 = 单元素）
        self._hover: TreeNode | None = None
        # 拖放源：文件行左键按下处（移过 startDragDistance 即发起拖拽）
        self._press_pos: QPoint | None = None
        self._press_node: TreeNode | None = None
        # 行布局缓存：每行起点 y（像素）＋结尾哨兵；幽灵行（预览改名）占两倍行高
        self._row_y: list[int] = [0]

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.verticalScrollBar().setSingleStep(int(T("size.tree.row.h")))
        self.viewport().setMouseTracking(True)
        ThemeManager.instance().theme_changed.connect(self.viewport().update)
        # 结构/状态变化后：自绘刷新 + 重排行布局（幽灵行改变行高，须同步滚动范围）
        self.model_changed.connect(self.viewport().update)
        self.model_changed.connect(self._relayout)

        self._rebuild_rows()

    def _relayout(self) -> None:
        """按行高重算每行起点并刷新滚动范围（model_changed 时同步执行）"""
        row_h = int(T("size.tree.row.h"))
        ys = [0]
        for node, _depth in self._rows:
            ys.append(ys[-1] + row_h * (2 if ghost_name(node) is not None else 1))
        self._row_y = ys
        self._update_scrollbar()

    # 数据
    def _walk(self, node: TreeNode, depth: int) -> None:
        for child in node.children:
            self._rows.append((child, depth))
            if child.is_dir and child.open:
                self._walk(child, depth + 1)

    def _rebuild_rows(self) -> None:
        self._rows = []
        self._walk(self._root, 0)
        self.model_changed.emit()

    def set_root(self, root: TreeNode) -> None:
        """替换树根并重建行列表（导入文件夹时用）"""
        self._root = root
        self._rebuild_rows()

    @staticmethod
    def _dir_state(node: TreeNode) -> int:
        """目录三态：0 = 不选，1 = 半选，2 = 全选（由子节点推导）"""
        if not node.children:
            return 0
        states = [
            TreeView._dir_state(c) if c.is_dir else (2 if c.checked else 0)
            for c in node.children
        ]
        if all(s == 2 for s in states):
            return 2
        if all(s == 0 for s in states):
            return 0
        return 1

    @staticmethod
    def _dir_status(node: TreeNode) -> Status | None:
        """目录子树的 worst 状态（FAILED/CONFLICT > SKIPPED）；无非成功返回 None"""
        worst: Status | None = None
        stack = list(node.children)
        while stack:
            c = stack.pop()
            if c.is_dir:
                stack.extend(c.children)
            elif c.status in (Status.FAILED, Status.CONFLICT):
                return c.status
            elif c.status is Status.SKIPPED:
                worst = Status.SKIPPED
        return worst

    def row_status(self, node: TreeNode) -> Status | None:
        """该行当前应显示的状态（None = 无标记）：文件取自身 status；目录仅在折叠时取子树聚合 worst"""
        if node.is_dir:
            if node.open:
                return None
            return self._dir_status(node)
        if node.status is None:
            return None
        return node.status if STATUS_STYLE[node.status][0] is not None else None

    @staticmethod
    def _set_all_checked(node: TreeNode, value: bool) -> None:
        node.checked = value
        for child in node.children:
            TreeView._set_all_checked(child, value)

    def _toggle_check(self, node: TreeNode) -> None:
        if node.is_dir:
            self._set_all_checked(node, self._dir_state(node) != 2)
        else:
            node.checked = not node.checked

    # 折叠 / 展开全部（右键菜单）
    def collapse_all(self) -> None:
        """全部目录折叠（含已展开的），重建行列表"""
        self._set_all_open(self._root, False)
        self._rebuild_rows()

    def expand_all(self) -> None:
        """全部目录展开，重建行列表"""
        self._set_all_open(self._root, True)
        self._rebuild_rows()

    @staticmethod
    def _set_all_open(node: TreeNode, value: bool) -> None:
        for child in node.children:
            if child.is_dir:
                child.open = value
                TreeView._set_all_open(child, value)

    # 几何
    def _update_scrollbar(self) -> None:
        sb = self.verticalScrollBar()
        sb.setRange(0, max(0, self.content_height() - self.viewport().height()))
        sb.setPageStep(self.viewport().height())

    def _row_at_y(self, y: int) -> int | None:
        """按内容坐标 y 定位所在行（行高不等，先查起点缓存再二分）"""
        ys = self._row_y
        n = len(self._rows)
        if n == 0:
            return None
        if y >= ys[-1]:
            return n - 1
        return max(0, min(n - 1, bisect_right(ys, y) - 1))

    def _hit(self, pos: QPoint) -> tuple[int | None, str | None]:
        """命中检测：返回 ``(行号, 子区域)``，子区域为 arrow / chk / body"""
        y = pos.y() + self.verticalScrollBar().value()
        i = self._row_at_y(y)
        if i is None:
            return None, None
        node, depth = self._rows[i]
        return i, hit_area(node, depth, QPoint(pos.x(), y - self._row_y[i]))

    # 事件
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            # 空白/目录/文件一律上报，菜单内容由调用方按目标判定；右键不改变选中
            i, _area = self._hit(event.pos())
            node = self._rows[i][0] if i is not None else None
            self.context_menu_requested.emit(node, event.globalPosition().toPoint())
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self._handle_left_press(event)

    def mouseDoubleClickEvent(self, event) -> None:
        """与单击同等处理：避免 Windows 双击判定吞掉快速连续展开/折叠"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._handle_left_press(event)
        else:
            super().mouseDoubleClickEvent(event)

    def _handle_left_press(self, event) -> None:
        """左键命中分发：箭头/目录行切换展开、复选框三态、文件行选中"""
        i, area = self._hit(event.pos())
        self._press_pos = None
        self._press_node = None
        if i is None:
            event.ignore()
            return
        node, _depth = self._rows[i]
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if node.is_dir and area in ("arrow", "body"):
            node.open = not node.open
            self._rebuild_rows()
        elif area == "chk":
            if node.is_dir:
                # 目录复选框只翻转子树三态，目录本身不可选中
                self._toggle_check(node)
            else:
                self._toggle_check(node)  # 被点文件先翻转自身
                if len(self._multi) > 1 and node in self._multi:
                    # 批量：整批统一到被点文件的新勾选状态
                    for f in self._multi:
                        if f is not node:
                            f.checked = node.checked
                else:
                    self._multi = {node}
                self.file_selected.emit(node)
            self.viewport().update()
            self.check_count_changed.emit(self.checked_file_count())
        elif not node.is_dir:
            if shift:
                self._select_range(node)
            else:
                self._multi = {node}
                self._anchor = node
            self._press_pos = event.pos()
            self._press_node = node
            self.file_selected.emit(node)
            self.viewport().update()
        event.accept()

    def _select_range(self, node: TreeNode) -> None:
        """Shift+左键：把「锚点到当前文件」行区间内的全部文件行批量选中"""
        if self._anchor is None or self._anchor is node:
            self._multi = {node}
            return
        idxs = [i for i, (n, _d) in enumerate(self._rows) if n in (self._anchor, node)]
        if len(idxs) != 2:
            self._multi = {node}
            return
        lo, hi = sorted(idxs)
        self._multi = {
            self._rows[i][0] for i in range(lo, hi + 1) if not self._rows[i][0].is_dir
        }

    def mouseMoveEvent(self, event) -> None:
        # 文件行按下后拖动越过系统阈值即发起拖拽（阻塞到放置/取消）
        if (
            self._press_node is not None
            and (event.buttons() & Qt.MouseButton.LeftButton)
            and (event.pos() - self._press_pos).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            self._start_drag(self._press_node)
            return
        i, _area = self._hit(event.pos())
        node = self._rows[i][0] if i is not None else None
        if node is not self._hover:
            self._hover = node
            self.viewport().update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """未拖拽的普通点击：清掉拖放源起点（拖拽结束由 _start_drag 自己清理）"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = None
            self._press_node = None
        super().mouseReleaseEvent(event)

    # 拖放源（文件到模板面板）
    def _start_drag(self, node: TreeNode) -> None:
        """自定义 MIME 保留真实路径，普通文本通道提供显示文件名。"""
        mime = QMimeData()
        source = str(node.path) if node.path is not None else node.name
        mime.setData(MIME_FILE, source.encode("utf-8"))
        mime.setText(node.name)
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(drag_pixmap(node.name, self.font()))
        drag.setHotSpot(QPoint(10, int(T("size.tree.row.h")) // 2))
        drag.exec_(Qt.DropAction.CopyAction)
        self._press_pos = None
        self._press_node = None

    def mouseLeaveEvent(self, event) -> None:
        if self._hover is not None:
            self._hover = None
            self.viewport().update()
        super().mouseLeaveEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_scrollbar()

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta:
            self.scroll_delta(-delta * self.row_step() // 120)
            event.accept()
        else:
            super().wheelEvent(event)

    # 供左侧专属滚动条（TreeScrollBar）使用
    def viewport_height(self) -> int:
        return self.viewport().height()

    def content_height(self) -> int:
        return self._row_y[-1]

    def row_starts(self) -> list:
        """每行起点 y 缓存（含结尾哨兵），供小地图按真实行高定位标记"""
        return self._row_y

    def scroll_value(self) -> int:
        return self.verticalScrollBar().value()

    def set_scroll_value(self, value: int) -> None:
        self.verticalScrollBar().setValue(int(value))

    def scroll_delta(self, delta: int) -> None:
        sb = self.verticalScrollBar()
        sb.setValue(sb.value() + int(delta))

    def row_step(self) -> int:
        return int(T("size.tree.row.h"))

    def collect_files(self) -> list:
        """收集全部文件节点（递归含折叠中目录），供执行统计/状态遍历使用"""
        out: list = []
        self._collect(self._root, out)
        return out

    def checked_file_count(self) -> int:
        """复选框勾选的文件总数（递归含折叠目录；目录行不计入）"""
        return sum(1 for f in self.collect_files() if f.checked)

    def checked_files(self) -> list:
        """勾选的文件节点（递归含折叠目录；目录行不计入），执行目标即此集合"""
        return [f for f in self.collect_files() if f.checked]

    def visible_rows(self) -> list:
        """当前实际显示的行 ``(node, depth)`` 列表，与自绘顺序一致（折叠目录的子行不出现）"""
        return list(self._rows)

    def is_selected(self, node: TreeNode) -> bool:
        """节点是否在当前选中集内（单选或 Shift 批量）"""
        return node in self._multi

    def _collect(self, node: TreeNode, out: list) -> None:
        for child in node.children:
            if child.is_dir:
                self._collect(child, out)
            else:
                out.append(child)

    def sizeHint(self) -> QSize:
        return QSize(320, 400)

    # 绘制
    def paintEvent(self, event) -> None:
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(event.rect(), QColor(T("color.bg.surface2")))
        n = len(self._rows)
        if n == 0:
            return
        offset = self.verticalScrollBar().value()
        ys = self._row_y
        first = self._row_at_y(offset) or 0
        # 可视窗口底沿以下第一个行起点为止的行都画（含跨界行）
        last = min(n, bisect_right(ys, offset + self.viewport().height()))
        for i in range(first, last):
            node, depth = self._rows[i]
            paint_row(
                painter,
                QRect(0, ys[i] - offset, self.viewport().width(), ys[i + 1] - ys[i]),
                node,
                depth,
                selected=node in self._multi,
                hovered=node is self._hover,
                status=self.row_status(node),
                check_state=self._dir_state(node)
                if node.is_dir
                else (2 if node.checked else 0),
            )
