from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from sr.app.errors import ApplicationError
from sr.app.models import Batch, Change, Direction, FileStamp, Ledger
from sr.app.protocols import FileSystem, StateStore


class RenameTransaction:
    """执行批次，并在中断后把成员收敛到旧名或新名。"""

    def __init__(self, filesystem: FileSystem, store: StateStore) -> None:
        """保存文件移动与账本持久化端口。"""
        self._filesystem = filesystem
        self._store = store

    def execute(self, batch: Batch, ledger: Ledger) -> Batch:
        """执行已准备临时路径的批次并结算账本。

        Args:
            batch: 已补好临时路径、准备执行的批次。
            ledger: 当前账本；调用方须持锁。
        Returns:
            更新状态与逐项错误后的 Batch。
        Raises:
            ApplicationError: 批次状态不允许执行，或文件位置无法确认。
            OSError: 写入账本失败。
        """
        if batch.status != "running":
            raise ApplicationError("只能执行 running 批次")
        running = ledger.running()
        if running is not None and running.id != batch.id:
            raise ApplicationError("存在其他未完成批次")

        # 先把执行意图写盘，再开始移动文件。
        ledger = ledger.with_batch(batch)
        self._store.save(ledger)

        changes = list(batch.changes)
        reached: list[int] = []
        for index, change in enumerate(changes):
            if not change.ready:
                continue
            try:
                start, _ = change.endpoints(batch.direction)
                self._move(start, self._temporary(change), change.stamp)
            except Exception as exc:  # noqa: BLE001 - 单文件失败写回自身
                changes[index] = replace(change, error=exc)
            else:
                reached.append(index)

        for index in reached:
            change = changes[index]
            try:
                _, end = change.endpoints(batch.direction)
                self._move(self._temporary(change), end, change.stamp)
            except Exception as exc:  # noqa: BLE001 - 单文件失败写回自身
                changes[index] = replace(change, error=exc)

        settled = all(self._is_settled(change) for change in changes)
        completed = replace(
            batch,
            status="completed" if settled else "running",
            updated=datetime.now(timezone.utc),
            changes=tuple(changes),
        )
        self._store.save(ledger.settle(completed))
        return completed

    def recover(
        self,
        batch: Batch,
        ledger: Ledger,
        *,
        direction: Direction,
        dry_run: bool = False,
    ) -> Batch:
        """把未完成批次的可执行成员收敛到指定方向。

        Args:
            batch: 状态为 running 的批次。
            ledger: 当前账本；调用方须持锁。
            direction: 目标方向。
            dry_run: 为 True 时只定位并标记错误，不移动或写盘。
        Returns:
            更新方向与状态后的 Batch。
        Raises:
            OSError: 写入账本失败。
        """
        locations = tuple(
            self._locate(change) if self._participates(change) else None
            for change in batch.changes
        )
        changes: list[Change] = []
        for change, current in zip(batch.changes, locations):
            changes.append(
                self._stage_recovery(change, current, direction, dry_run=dry_run)
            )
        if not dry_run:
            for index, change in enumerate(changes):
                if change.error is None:
                    changes[index] = self._converge(change, direction)
        converged = not dry_run and all(
            self._has_reached(change, direction)
            for change in changes
            if self._participates(change)
        )
        updated = replace(
            batch,
            direction=direction,
            status="completed" if converged else "running",
            updated=datetime.now(timezone.utc),
            changes=tuple(changes),
        )
        if dry_run:
            return updated
        self._store.save(ledger.settle(updated))
        return updated

    def _stage_recovery(
        self,
        change: Change,
        current: Path | None,
        direction: Direction,
        *,
        dry_run: bool,
    ) -> Change:
        """把尚未到达终点的成员移到临时路径，腾出循环占位。"""
        if not self._participates(change):
            return change
        if current is None:
            return replace(
                change,
                error=ApplicationError(f"无法确认文件位置：{change.source}"),
            )
        destination = change.endpoints(direction)[1]
        if self._filesystem.key(current) == self._filesystem.key(destination):
            return replace(change, error=None)
        if dry_run:
            return change
        try:
            temporary = self._temporary(change)
            if self._filesystem.key(current) != self._filesystem.key(temporary):
                self._move(current, temporary, change.stamp)
        except (OSError, ValueError, ApplicationError) as exc:
            return replace(change, error=exc)
        return replace(change, error=None)

    def _converge(self, change: Change, direction: Direction) -> Change:
        """把已暂存的成员收敛到指定方向的端点。"""
        if not self._participates(change):
            return change
        current = self._locate(change)
        if current is None:
            return replace(
                change,
                error=ApplicationError(f"无法确认文件位置：{change.source}"),
            )
        destination = change.endpoints(direction)[1]
        if self._filesystem.key(current) == self._filesystem.key(destination):
            return replace(change, error=None)
        try:
            self._move(current, destination, change.stamp)
        except (OSError, ValueError, ApplicationError) as exc:
            return replace(change, error=exc)
        return replace(change, error=None)

    def _locate(self, change: Change) -> Path | None:
        """在源、临时和目标位置中按快照唯一定位文件。"""
        matches: list[Path] = []
        keys: set[tuple[int, int, str]] = set()
        for candidate in (change.source, change.temporary, change.target):
            if candidate is None or not self._stamp_matches(candidate, change.stamp):
                continue
            key = self._filesystem.key(candidate)
            if key in keys:
                continue
            keys.add(key)
            matches.append(candidate)
        return matches[0] if len(matches) == 1 else None

    def _participates(self, change: Change) -> bool:
        """判断成员是否可能在磁盘上留有文件，需要参与收敛。"""
        if change.target is None:
            return False
        return change.error is None or change.temporary is not None

    def _is_settled(self, change: Change) -> bool:
        """判断成员是否停在可确认且非临时路径的位置。"""
        if change.temporary is None:
            return True
        current = self._locate(change)
        return current is not None and current != change.temporary

    def _has_reached(self, change: Change, direction: Direction) -> bool:
        """判断成员是否已停在指定方向的端点。"""
        current = self._locate(change)
        if current is None:
            return False
        destination = change.endpoints(direction)[1]
        return self._filesystem.key(current) == self._filesystem.key(destination)

    def _move(self, source: Path, target: Path, stamp: FileStamp) -> None:
        """移动一步；失败时判断文件是否其实已经移动。"""
        if not self._stamp_matches(source, stamp):
            raise ApplicationError(f"源文件已变化：{source}")
        try:
            self._filesystem.rename(source, target)
        except (OSError, ValueError, ApplicationError) as cause:
            source_matches = self._stamp_matches(source, stamp)
            target_matches = self._stamp_matches(target, stamp)
            if target_matches and not source_matches:
                return
            if source_matches and not target_matches:
                raise
            raise ApplicationError(f"无法确定文件位置：{source} / {target}") from cause

    def _stamp_matches(self, path: Path, stamp: FileStamp) -> bool:
        """判断路径当前状态是否仍与预期快照一致。"""
        try:
            return self._filesystem.stat(path) == stamp
        except (OSError, ValueError):
            return False

    def _temporary(self, change: Change) -> Path:
        """取出执行时必须存在的临时路径。"""
        if change.temporary is None:
            raise ValueError("缺少临时路径")
        return change.temporary
