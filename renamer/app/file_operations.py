"""文件变更用例：先记录再改名、失败抵消，以及按批次撤销"""

from __future__ import annotations

from renamer.core.model import FileResult, Issue, Level, Status, UndoRecord
from renamer.core.ports import FileSystem, Logger, UndoLog


class FileOperations:
    """持有文件系统和撤销日志，执行已求值条目的变更与撤销"""

    def __init__(
        self,
        filesystem: FileSystem,
        undo_log: UndoLog,
        logger: Logger | None = None,
    ) -> None:
        self.filesystem = filesystem
        self._undo_log = undo_log
        self._logger = logger

    def undo(
        self, log_id: str | None = None
    ) -> tuple[str | None, int, list[UndoRecord]]:
        """撤销指定或最近一次改名，返回实际 log_id、还原条数与还原记录

        直接消费 `UndoLog.undo`，由其执行真实改名并返回记录

        Args:
            log_id: 目标批次 id，None 表示最近一次

        Returns:
            (实际 log_id, 还原条数, 还原记录列表)，无可撤销时记录列表为空
        """
        applied = self._undo_log.undo(log_id)
        if log_id is not None:
            actual, restored = log_id, len(applied)
        else:
            actual = applied[0].log_id if applied else None
            restored = len(applied)
        self._log("undo", log_id=actual, restored=restored)
        return actual, restored, applied

    def apply(self, item: FileResult, log_id: str) -> None:
        """改名前写撤销日志，改名失败抵消记录并把条目降级为 FAILED"""
        source = item.source
        target_name = item.target
        if target_name is None:
            item.status = Status.FAILED
            item.issues.append(
                Issue(level=Level.ERROR, code="rename_failed", message="目标名为空")
            )
            return
        target_path = source.parent / target_name
        self._undo_log.append(log_id, str(source), str(target_path))
        try:
            self.filesystem.rename(source, target_path)
        except OSError as exc:
            self._undo_log.cancel(log_id, str(source), str(target_path))
            item.status = Status.FAILED
            item.issues.append(
                Issue(
                    level=Level.ERROR, code="rename_failed", message=f"改名失败: {exc}"
                )
            )
            return
        self._log("rename", log_id=log_id, source=str(source), target=str(target_path))

    def _log(self, event: str, **fields: object) -> None:
        """经 Logger 端口发结构化事件，未注入则跳过"""
        if self._logger is not None:
            self._logger.log({"event": event, **fields})
