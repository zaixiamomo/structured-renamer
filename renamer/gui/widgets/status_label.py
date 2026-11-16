"""语义状态标签：组件只声明状态，颜色由全局 QSS 决定。"""

from typing import Literal

from PySide6.QtWidgets import QLabel

__all__ = ["StatusLabel"]


class StatusLabel(QLabel):
    """沿用 QLabel 的布局与文本接口，支持成功、警告、错误和默认文字色。"""

    def set_status(self, status: Literal["", "ok", "warn", "err"]) -> None:
        """切换语义状态；空值恢复当前 role 的默认文字色。"""
        if self.property("status") == status:
            return
        self.setProperty("status", status)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
