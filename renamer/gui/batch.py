"""批量操作的 GUI 协调：保留节点身份、回填结果并通知展示刷新"""

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from renamer.app import Status

from .execution_contracts import Executor, RunOutcome
from .state.files import TreeNode


class BatchCoordinator(QObject):
    files_changed = Signal()
    message_changed = Signal(str)
    run_info_changed = Signal(object)

    def __init__(
        self,
        executor: Executor,
        collect_files: Callable[[], list[TreeNode]],
        parent=None,
    ):
        super().__init__(parent)
        self._executor = executor
        self._collect_files = collect_files
        self._last_files: list[TreeNode] = []

    def run(self, files, rule_names, *, preview: bool) -> None:
        self._last_files = files
        paths = [node.path for node in files if node.path is not None]
        method = self._executor.preview if preview else self._executor.apply
        method(paths, rule_names, lambda out: self._on_run_done(out, preview=preview))

    def _on_run_done(self, outcome: RunOutcome, *, preview: bool) -> None:
        for node in self._collect_files():
            node.status = None
        for node, item in zip(self._last_files, outcome.items):
            node.status = item.status
            if item.status is Status.SUCCESS and item.target is not None:
                if preview:
                    node.rename = (
                        item.target.name if item.target.name != node.name else None
                    )
                else:
                    node.rename = None
                    node.name = item.target.name
                    node.path = node.path.parent / item.target.name
            else:
                node.rename = None
        self.files_changed.emit()
        if outcome.plan_error:
            self.message_changed.emit(self._issue_text(outcome.plan_error))
        else:
            self.run_info_changed.emit(self._counts(outcome.items))

    def clear(self) -> None:
        for node in self._collect_files():
            node.status = None
        self.files_changed.emit()
        self.run_info_changed.emit(None)

    def undo(self) -> None:
        self._executor.undo(self._on_undo_done)

    def _on_undo_done(self, outcome: RunOutcome) -> None:
        all_files = self._collect_files()
        if outcome.items:
            by_path = {node.path: node for node in all_files if node.path is not None}
            for item in outcome.items:
                node = by_path.get(item.source)
                if node is not None and item.target is not None:
                    node.name = item.target.name
                    node.path = node.path.parent / item.target.name
                    node.rename = None
            self.files_changed.emit()
        self.message_changed.emit(outcome.message or "已撤销（无记录）")

    @staticmethod
    def _counts(items) -> tuple[int, int, int]:
        ok = sum(1 for item in items if item.status is Status.SUCCESS)
        warn = sum(1 for item in items if item.status is Status.SKIPPED)
        fail = sum(
            1 for item in items if item.status in (Status.FAILED, Status.CONFLICT)
        )
        return ok, warn, fail

    @staticmethod
    def _issue_text(issues) -> str:
        return "；".join(f"{issue.code}: {issue.message}" for issue in issues)
