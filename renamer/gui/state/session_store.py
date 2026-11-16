"""已保存会话的 Qt 变更桥，不另存声明状态"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from renamer.app.session import AuthoringSession
from renamer.core.model import Library, ParseTemplate, RenderTemplate, Rule, Template

__all__ = ["SessionStore"]


class SessionStore(QObject):
    """Qt 适配：包一个 AuthoringSession，把变更广播为 Qt 信号"""

    changed = Signal()

    def __init__(self, authoring_session: AuthoringSession, parent=None) -> None:
        super().__init__(parent)
        self._session = authoring_session
        unsubscribe = self._session.subscribe(self.changed.emit)
        self.destroyed.connect(lambda: unsubscribe())

    @property
    def authoring_session(self) -> AuthoringSession:
        return self._session

    # 工作集字典按需取（load 会整表重赋，属性避免陈旧引用）
    @property
    def templates(self) -> dict[str, Template]:
        return self._session.templates

    @property
    def parse_templates(self) -> dict[str, ParseTemplate]:
        return self._session.parse_templates

    @property
    def render_templates(self) -> dict[str, RenderTemplate]:
        return self._session.render_templates

    @property
    def rules(self) -> dict[str, Rule]:
        return self._session.rules

    @property
    def library(self) -> Library:
        return self._session.library

    def get_rule(self, name: str) -> Rule | None:
        return self._session.get_rule(name)

    def template_names(self) -> list[str]:
        """模板编辑入口只列解析模板，角色由模型决定而非名称后缀"""
        return list(self._session.parse_templates)

    def rule_names(self) -> list[str]:
        return self._session.rule_names()
