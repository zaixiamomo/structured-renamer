"""执行改名操作并在失败时回滚。"""

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from sr.app.errors import ApplicationError, StateWriteError
from sr.app.models import (
    ExecutionReport,
    MoveIntent,
    RenameOperation,
)
from sr.app.protocols import FileSystem


class RenameExecutor:
    """按两步改名执行操作，保证可恢复和可回滚。"""

    def __init__(self, filesystem: FileSystem) -> None:
        """保存文件系统端口。"""
        self._filesystem = filesystem

    def reconcile(self, operation: RenameOperation) -> RenameOperation:
        """根据文件戳确认中断改名后的实际位置。

        Args:
            operation: 带有 pending MoveIntent 的操作。
        Returns:
            已清除 pending 并更新 actual_path 的操作。
        Raises:
            ApplicationError: 两个候选位置中无法唯一确认一个匹配。
        """
        if operation.pending is None:
            return operation
        index = operation.pending.index
        change = operation.changes[index]
        # pending 记录移动前的位置和目标，用 stamp 判断文件最终落在哪边。
        candidates = (change.actual_path, operation.pending.target)
        matches = []
        for path in candidates:
            try:
                if self._filesystem.stat(path) == change.stamp:
                    matches.append(path)
            except (OSError, ValueError):
                continue
        if len(matches) != 1:
            raise ApplicationError(
                f"无法确认中断改名后的文件位置，保留状态：{candidates[0]} / {candidates[1]}"
            )
        return operation.confirm(index, matches[0])

    def execute(
        self,
        operation: RenameOperation,
        *,
        checkpoint: Callable[[RenameOperation], None],
        restoring: bool = False,
    ) -> ExecutionReport:
        """执行改名操作。

        先把所有需要移动的成员改成临时名，再移到最终目标，从而支持目录内互换和循环。
        每次移动前后都会 checkpoint；普通失败会按相反顺序回滚已完成的步骤。

        Args:
            operation: 已确认位置、无 pending 的操作。
            checkpoint: 保存进度的回调；失败时终止且不再回滚，交由 --undo 恢复。
            restoring: 为 True 时目标是 source（恢复），否则是 target。
        Returns:
            包含 before/after 和错误（含回滚错误）的 ExecutionReport。
        Raises:
            ApplicationError: 操作仍有 pending，或中断后无法确认文件位置。
            StateWriteError: checkpoint 保存失败。
        """
        if operation.pending is not None:
            raise ApplicationError("请先确认待执行操作和未完成改名的文件位置")
        before = operation
        destinations = tuple(
            c.source if restoring else c.target for c in operation.changes
        )
        moving = [
            i
            for i, c in enumerate(operation.changes)
            if str(c.actual_path) != str(destinations[i])
        ]
        steps: list[tuple[int, Path, Path]] = []
        # 本批出现过的所有路径都不可再用作临时名。
        reserved = {
            self._filesystem.key(path)
            for c in operation.changes
            for path in (c.source, c.target, c.actual_path)
        }

        def _record(progress: RenameOperation) -> None:
            """更新操作快照并同步保存进度。"""
            # 先保存意图再移动，让中断后的对账知道目标位置。
            nonlocal operation
            operation = progress
            try:
                checkpoint(progress)
            except Exception as exc:
                raise StateWriteError(
                    "保存改名进度失败，停止操作；请恢复状态存储后 undo"
                ) from exc

        def _move(index: int, target: Path, *, remember: bool = False) -> None:
            """执行单步移动并记录可回滚步骤。"""
            change = operation.changes[index]
            source = change.actual_path
            if self._filesystem.stat(source) != change.stamp:
                raise ApplicationError(f"源文件已变化：{source}")
            _record(replace(operation, pending=MoveIntent(index, target)))
            try:
                self._filesystem.rename(source, target)
            except Exception:
                # 失败后先对账；只有文件确实移动了才记入回滚步骤。
                _record(self.reconcile(operation))
                if remember and str(operation.changes[index].actual_path) == str(
                    target
                ):
                    steps.append((index, source, target))
                raise
            _record(operation.confirm(index, target))
            if remember:
                steps.append((index, source, target))

        try:
            # 第一阶段全部改到临时名，第二阶段再落到目标，避免占位和循环冲突。
            for index in moving:
                source = operation.changes[index].actual_path
                while True:
                    temporary = source.with_name(f".sr-{uuid4().hex}.tmp")
                    key = self._filesystem.key(temporary)
                    if key not in reserved and not self._filesystem.exists(temporary):
                        reserved.add(key)
                        break
                _move(index, temporary, remember=True)
            for index in moving:
                _move(index, destinations[index], remember=True)
        except StateWriteError:
            raise
        except Exception as exc:
            if operation.pending is not None:
                raise
            recovery_errors = []
            # 逆序回滚；成员已不在预期位置时停止，保留可恢复状态。
            for index, source, target in reversed(steps):
                try:
                    if str(operation.changes[index].actual_path) != str(target):
                        raise ApplicationError(
                            f"尚未恢复后续改名，保留当前位置：{operation.changes[index].actual_path}"
                        )
                    _move(index, source)
                except StateWriteError:
                    raise
                except Exception as recovery:
                    if operation.pending is not None:
                        raise
                    recovery_errors.append(recovery)
            return ExecutionReport(before, operation, exc, tuple(recovery_errors))
        return ExecutionReport(before, operation)
