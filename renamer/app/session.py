"""已保存声明的会话工作集，持久化成功后发布状态与变更通知"""

from __future__ import annotations

from collections.abc import Callable

from renamer.adapters.library_file import LibraryFile
from renamer.core.model import (
    Library,
    ParseTemplate,
    RenderTemplate,
    Rule,
    Template,
)


class AuthoringSession:
    """持有已保存的模板和规则，向各编辑器提供独立库快照"""

    def __init__(self, storage: LibraryFile) -> None:
        self.parse_templates: dict[str, ParseTemplate] = {}
        self.render_templates: dict[str, RenderTemplate] = {}
        self.rules: dict[str, Rule] = {}
        self._storage = storage
        self._listeners: list[Callable[[], None]] = []

    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        """订阅变更，返回可重复调用的解除订阅函数"""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    @property
    def templates(self) -> dict[str, Template]:
        merged = dict(self.render_templates)
        merged.update(self.parse_templates)
        return merged

    @property
    def library(self) -> Library:
        """当前库的独立快照，调用方修改字典不会改变会话"""
        return Library(
            parse_templates=dict(self.parse_templates),
            render_templates=dict(self.render_templates),
            rules=dict(self.rules),
        )

    # 写
    def update_library(self, library: Library) -> None:
        """合并整片库，持久化成功后一次提交内存并通知

        三类条目各按名称覆盖，未提供的条目保留。序列化或文件替换失败时
        抛出原异常，当前会话和已存文件保持不变，不发送变更通知。
        """
        merged = Library(
            parse_templates={**self.parse_templates, **library.parse_templates},
            render_templates={**self.render_templates, **library.render_templates},
            rules={**self.rules, **library.rules},
        )
        self._storage.write(merged)
        self.parse_templates = dict(merged.parse_templates)
        self.render_templates = dict(merged.render_templates)
        self.rules = dict(merged.rules)
        self._notify()

    def add_template(self, name: str, template: Template) -> None:
        if isinstance(template, ParseTemplate):
            library = Library(parse_templates={name: template})
        elif isinstance(template, RenderTemplate):
            library = Library(render_templates={name: template})
        else:
            raise TypeError(
                f"模板 {name!r} 缺少角色：须为 ParseTemplate 或 RenderTemplate"
            )
        self.update_library(library)

    def add_rule(self, name: str, rule: Rule) -> None:
        self.update_library(Library(rules={name: rule}))

    # 读
    def get_template(self, name: str) -> Template | None:
        return self.parse_templates.get(name) or self.render_templates.get(name)

    def get_rule(self, name: str) -> Rule | None:
        return self.rules.get(name)

    def rule_names(self) -> list[str]:
        return list(self.rules)

    def load(self) -> None:
        """读取已保存库；不可读取时保留当前状态"""
        library = self._storage.read()
        if library is None:
            return
        self.parse_templates = dict(library.parse_templates)
        self.render_templates = dict(library.render_templates)
        self.rules = dict(library.rules)
        self._notify()
