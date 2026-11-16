"""应用用例的后台适配，不读取控件或修改文件树节点"""

from pathlib import Path

from renamer.app import FileResult, Issue, Level, RenameService, Status
from renamer.app.authoring import Library, PlanError
from renamer.app.capability_trial import CapabilityTrial

from .background import BackgroundWorker
from .execution_contracts import RunOutcome
from .state.session_store import SessionStore


class ServiceExecutor(BackgroundWorker):
    def __init__(
        self, service: RenameService, session_store: SessionStore, parent=None
    ):
        super().__init__(parent)
        self._service = service
        self._session = session_store

    def preview(self, paths, rule_names, on_done) -> None:
        self._run(paths, rule_names, dry_run=True, on_done=on_done)

    def apply(self, paths, rule_names, on_done) -> None:
        self._run(paths, rule_names, dry_run=False, on_done=on_done)

    def undo(self, on_done) -> None:
        def work() -> RunOutcome:
            _log_id, count, applied = self._service.undo(None)
            items = [
                FileResult(
                    source=Path(rec.old), target=Path(rec.new), status=Status.SUCCESS
                )
                for rec in applied
            ]
            return RunOutcome(
                items=items,
                message=f"已撤销 {count} 条改名" if count else "无可撤销记录",
            )

        self.submit(work, on_done, self._on_error)

    def _run(self, paths, rule_names, *, dry_run: bool, on_done) -> None:
        def work() -> RunOutcome:
            lib = Library(
                parse_templates=self._session.parse_templates,
                render_templates=self._session.render_templates,
                rules=self._session.rules,
            )
            self._service.with_library(lib)
            try:
                report = self._service.run(rule_names, paths, dry_run=dry_run)
            except PlanError as exc:
                return RunOutcome(items=[], plan_error=exc.issues)
            return RunOutcome(items=list(report.items))

        self.submit(work, on_done, self._on_error)

    @staticmethod
    def _on_error(exc: Exception) -> RunOutcome:
        return RunOutcome(
            items=[],
            plan_error=[
                Issue(
                    level=Level.ERROR, code="internal_error", message=f"执行异常：{exc}"
                )
            ],
        )


class ServiceCapabilityRunner(BackgroundWorker):
    def __init__(self, trial: CapabilityTrial, parent=None):
        super().__init__(parent)
        self._trial = trial

    def run(self, cap_id, inputs, on_done) -> None:
        self.submit(lambda: self._trial.run(cap_id, inputs), on_done, self._on_error)

    @staticmethod
    def _on_error(exc: Exception) -> dict:
        return {}
