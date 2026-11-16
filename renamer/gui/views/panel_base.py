"""编辑面板公共基类：模板面板与规则面板共享的骨架与工具"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from ..widgets.tree_view import MIME_FILE

__all__ = ["EditorPanel"]


class EditorPanel(QWidget):
    """编辑窗口面板基类（模板 / 规则共用）"""

    # 面板内容所需宽度变化（词流增删），侧面板据此收紧抽屉下限
    content_changed = Signal()
    # 面板名变化（顶栏改名），侧面板据此同步标题栏
    name_changed = Signal()
    # 面板请求聚焦名称编辑处（模板 TOML 内点 name 高亮），侧面板据此聚焦标题栏
    name_edit_requested = Signal()

    # 对外契约（侧面板直接调用）
    @property
    def name(self) -> str:
        """当前编辑对象名（侧面板标题栏读口）"""
        raise NotImplementedError

    def set_name(self, name: str) -> None:
        """顶栏重命名（侧面板标题栏写口）"""
        raise NotImplementedError

    def save(self) -> bool:
        """校验并登记到会话存储；返回 True 表示可关闭侧边窗口"""
        raise NotImplementedError

    def set_filename(self, text: str) -> None:
        """注入示例文件名（文件树拖入 / 新建时自带选中文件）"""
        raise NotImplementedError

    def attach_scroll_area(self, scroll_area: QScrollArea) -> None:
        """接入宿主滚动区，规则页据此定位词池，其余面板无需处理"""

    # 拖放（文件树到面板）
    def dragEnterEvent(self, event) -> None:
        if self._drop_name(event) is not None:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if self._drop_name(event) is not None:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        name = self._drop_name(event)
        if name is not None:
            self.set_filename(name)
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()

    @staticmethod
    def _drop_name(event) -> str | None:
        """从拖放事件提取文件名：优先自定义 MIME（文件树拖入），回退 text/plain"""
        md = event.mimeData()
        data = md.data(MIME_FILE)
        if data:
            try:
                return bytes(data).decode("utf-8")
            except UnicodeDecodeError:
                return None
        if md.hasText():
            return md.text()
        return None

    # 页面与卡片布局
    def _make_layout(self) -> QVBoxLayout:
        """页面外层布局：统一两种编辑页的留白与分区间距。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)
        return layout

    @staticmethod
    def _pane_cap(text: str) -> QLabel:
        """卡片上方的分区标题（panel-title 样式，wordWrap 打开防撑宽）"""
        cap = QLabel(text)
        cap.setProperty("role", "panel-title")
        cap.setWordWrap(True)
        return cap
