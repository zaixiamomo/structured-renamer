"""多窗口状态机：id / 类型 / 身份色 / 三态 / 缩略序号"""

from collections.abc import Collection
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from ..theme import IDENTITY_COUNT, IDENTITY_KEYS, T

__all__ = ["Window", "WindowManager"]


@dataclass
class Window:
    """编辑窗口记录"""

    id: int
    type: str  # "template" / "rule"
    filename: str
    title: str
    identity_idx: int
    collapsed: bool = False


class WindowManager(QObject):
    """编辑窗口状态机：open / switch_to / collapse / close"""

    # 新窗口已建立（参数为 Window）
    window_opened = Signal(object)
    # 任何窗口结构 / 状态变化（缩略列与侧面板据此刷新）
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._windows: dict[int, Window] = {}
        self._order: list[int] = []
        self._active_id: int | None = None
        self._seq = 0
        # 窗口名占用（win.id 对应当前名），新建模板/规则防重号用，随 open/close 增删
        self._name_use: dict[int, str] = {}

    # 只读
    @property
    def windows(self) -> list:
        """按打开顺序返回全部窗口"""
        return [self._windows[i] for i in self._order]

    def active_window(self) -> Window | None:
        """当前前端窗口（侧面板显示它），全部缩略或无窗口时为 None"""
        return self._windows.get(self._active_id) if self._active_id else None

    def is_active(self, win: Window) -> bool:
        return win.id == self._active_id

    def identity_color(self, win: Window) -> str:
        """当前系列下该窗口的身份色"""
        return T(IDENTITY_KEYS[win.identity_idx % IDENTITY_COUNT])

    # 名字占用（新建防重号，跨窗口共享）
    def register_name(self, win_id: int, name: str) -> None:
        """登记窗口当前名（模板/规则面板在改名时调用）"""
        self._name_use[win_id] = name

    def is_name_taken(self, name: str, exclude_id: int | None = None) -> bool:
        """名字是否被其他已打开窗口占用（exclude_id 排除自身，允许复用旧名）"""
        return any(n == name for wid, n in self._name_use.items() if wid != exclude_id)

    def available_name(
        self, prefix: str, saved_names: Collection[str], exclude_id: int
    ) -> str:
        """取会话与其它打开窗口都未占用的第一个编号名称"""
        number = 1
        while f"{prefix}_{number}" in saved_names or self.is_name_taken(
            f"{prefix}_{number}", exclude_id
        ):
            number += 1
        return f"{prefix}_{number}"

    def _drop_window(self, win_id: int) -> None:
        """释放窗口的名字占用（close 内调用）"""
        self._name_use.pop(win_id, None)

    # 操作
    def open(
        self, type_: str, filename: str | None = None, title: str | None = None
    ) -> Window:
        """新建窗口并置为前端"""
        self._seq += 1
        default_name = "（新建模板）" if type_ == "template" else "（新建规则）"
        default_title = "新建模板" if type_ == "template" else "新建规则"
        win = Window(
            id=self._seq,
            type=type_,
            filename=filename or default_name,
            title=title or filename or default_title,
            identity_idx=self._seq - 1,
        )
        self._windows[win.id] = win
        self._order.append(win.id)
        self._active_id = win.id
        self.window_opened.emit(win)
        self.changed.emit()
        return win

    def switch_to(self, win_id: int) -> None:
        """切换前端（点浅色块 / 点缩略块恢复）"""
        win = self._windows.get(win_id)
        if win is None:
            return
        if win.collapsed:
            win.collapsed = False
        self._active_id = win_id
        self.changed.emit()

    def collapse(self, win_id: int) -> None:
        """缩略前端窗口（仅前端可被缩略）并收起抽屉"""
        win = self._windows.get(win_id)
        if win is None or win.collapsed or win.id != self._active_id:
            return
        win.collapsed = True
        self._active_id = None
        self.changed.emit()

    def close(self, win_id: int) -> None:
        """彻底删除窗口；若关掉的是前端则激活下一个"""
        if win_id not in self._windows:
            return
        del self._windows[win_id]
        self._order.remove(win_id)
        self._drop_window(win_id)
        if self._active_id == win_id:
            self._active_id = None
            for i in self._order:
                if not self._windows[i].collapsed:
                    self._active_id = i
                    break
            else:
                if self._order:
                    self._active_id = self._order[0]
        self.changed.emit()

    def close_active(self) -> None:
        if self._active_id is not None:
            self.close(self._active_id)
