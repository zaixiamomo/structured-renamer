from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sr.app.errors import ApplicationError, UnfinishedBatchError
from sr.app.models import Batch, HistoryEntry, Ledger
from sr.app.planner import RenamePlanner
from sr.app.preflight import RenamePreflight
from sr.app.protocols import FileSystem, RuleCodec, StateStore
from sr.app.transaction import RenameTransaction
from sr.core.compile.rule import Rule
from sr.plugin import ExtenderResources, PluginCatalog


class RenameService:
    """rename、undo、redo 与历史查询的用例入口。"""

    def __init__(
        self,
        filesystem: FileSystem,
        codec: RuleCodec,
        store: StateStore,
        *,
        catalog: PluginCatalog | None = None,
        resources: ExtenderResources | None = None,
        max_workers: int = 8,
    ) -> None:
        """保存用例依赖并校验线程数。

        Args:
            filesystem: 文件系统端口。
            codec: 规则编解码端口。
            store: 全局状态存储端口。
            catalog: 插件能力目录；省略时使用空目录。
            resources: 拓展资源；省略时使用无资源集合。
            max_workers: 分组求值线程数，必须是正整数。
        Raises:
            ValueError: max_workers 不是正整数。
        """
        self._filesystem = filesystem
        self._store = store
        self._transaction = RenameTransaction(filesystem, store)
        self._preflight = RenamePreflight(filesystem)
        self._planner = RenamePlanner(
            filesystem,
            codec,
            catalog=catalog,
            resources=resources,
            max_workers=max_workers,
        )

    def rename(
        self,
        directory: Path | str,
        rule: Rule | Path | str,
        *,
        dry_run: bool = False,
    ) -> Batch:
        """预览或执行一批改名。

        Args:
            directory: 待处理目录。
            rule: Rule 对象或 YAML 规则文件路径。
            dry_run: 为 True 时只返回批次，不移动文件。
        Returns:
            检查后的 Batch；dry_run 或没有可执行成员时直接返回。
        Raises:
            ApplicationError: 存在未完成批次或状态不满足执行条件。
            OSError: 读取规则、扫描目录或写入账本失败。
            ValueError: 规则解析或编译失败。
            PipelineError: 核心管线前置条件不满足。
        """
        directory = self._filesystem.resolve(Path(directory).expanduser().absolute())
        self._store.validate_target(directory)
        with self._locked_ledger() as ledger:
            self._ensure_idle(ledger)
            excluded = self._excluded_temporaries(directory, ledger)

        batch = self._planner.rename(directory, rule)
        if excluded:
            batch = replace(
                batch,
                changes=tuple(
                    change for change in batch.changes if change.source not in excluded
                ),
            )
        batch = self._preflight.check(batch, check_names=True)
        if dry_run or not batch.movable:
            return batch

        batch = self._prepare(batch)
        with self._locked_ledger() as ledger:
            self._ensure_idle(ledger)
            # 新 rename 持久化时清空 redo 栈。
            return self._transaction.execute(batch, ledger.clear_redo())

    def undo(
        self,
        *,
        batch_id: str | None = None,
        dry_run: bool = False,
    ) -> Batch:
        """把未完成批次收敛到旧名，或撤销指定的成功批次。

        Args:
            batch_id: 完整批次标识或唯一前缀；省略时选择全局最新成功批次。
            dry_run: 为 True 时只返回计划，不移动文件。
        Returns:
            更新后的 Batch。
        Raises:
            ApplicationError: 没有可撤销批次或状态不允许执行。
            OSError: 访问文件系统或写入账本失败。
        """
        with self._locked_ledger() as ledger:
            running = ledger.running()
            if running is not None:
                self._check_recovery(ledger, running, batch_id)
                return self._transaction.recover(
                    running, ledger, direction="backward", dry_run=dry_run
                )
            batch = self._undo_target(ledger, batch_id)
            batch = replace(
                batch,
                direction="backward",
                status="running",
                updated=self._now(),
            )
            batch = self._preflight.check(batch, check_names=False)
            if dry_run or not batch.movable:
                return batch
            batch = self._prepare(batch)
            return self._transaction.execute(batch, ledger)

    def redo(
        self,
        *,
        batch_id: str | None = None,
        dry_run: bool = False,
    ) -> Batch:
        """把未完成批次收敛到新名，或重做指定的已撤销批次。

        Args:
            batch_id: 完整批次标识或唯一前缀；省略时选择 redo 栈顶批次。
            dry_run: 为 True 时只返回计划，不移动文件。
        Returns:
            更新后的 Batch。
        Raises:
            ApplicationError: 没有可重做批次或状态不允许执行。
            OSError: 访问文件系统或写入账本失败。
        """
        with self._locked_ledger() as ledger:
            running = ledger.running()
            if running is not None:
                self._check_recovery(ledger, running, batch_id)
                return self._transaction.recover(
                    running, ledger, direction="forward", dry_run=dry_run
                )
            batch = self._redo_target(ledger, batch_id)
            batch = replace(
                batch,
                direction="forward",
                status="running",
                updated=self._now(),
            )
            batch = self._preflight.check(batch, check_names=True)
            if dry_run or not batch.movable:
                return batch
            batch = self._prepare(batch)
            return self._transaction.execute(batch, ledger)

    def find_batch(self, batch_id: str) -> Batch:
        """按标识返回批次快照。

        Args:
            batch_id: 完整批次标识或不产生歧义的前缀。
        Returns:
            账本中标识匹配的批次。
        Raises:
            ApplicationError: 批次不存在、账本损坏或状态文件无法读取。
        """
        with self._locked_ledger() as ledger:
            return self._require_batch(ledger, batch_id)

    def history(self, directory: Path | str | None = None) -> tuple[HistoryEntry, ...]:
        """从新到旧返回全部批次及其可重做状态。

        Args:
            directory: 只返回该目录的批次；省略时返回全部。
        Returns:
            按更新时间倒序排列的历史快照。
        Raises:
            ApplicationError: 账本损坏或包含旧版状态。
            OSError: 状态文件无法读取。
        """
        directory = self._filter_directory(directory)
        with self._locked_ledger() as ledger:
            redoable = set(ledger.redo_stack)
            entries = (
                HistoryEntry(batch, batch.id in redoable)
                for batch in ledger.batches
                if directory is None or batch.dir == directory
            )
            return tuple(
                sorted(entries, key=lambda entry: entry.batch.updated, reverse=True)
            )

    @contextmanager
    def _locked_ledger(self) -> Iterator[Ledger]:
        """持有全局锁并读取当前账本。"""
        with self._store.lock():
            yield self._store.load()

    def _ensure_idle(self, ledger: Ledger) -> None:
        """拒绝在存在未完成批次时开始新批次。"""
        running = ledger.running()
        if running is not None:
            raise UnfinishedBatchError(running)

    def _check_recovery(
        self,
        ledger: Ledger,
        batch: Batch,
        batch_id: str | None,
    ) -> None:
        """拒绝用其他标识恢复未完成批次。"""
        if batch_id is not None:
            requested = self._require_batch(ledger, batch_id)
            if requested.id != batch.id:
                raise ApplicationError(
                    f"批次 {batch.short_id} 尚未完成，"
                    f"无法处理批次 {requested.short_id}；"
                    f'请先运行 sr undo --id "{batch.short_id}" '
                    f'或 sr redo --id "{batch.short_id}"'
                )

    def _undo_target(
        self,
        ledger: Ledger,
        batch_id: str | None,
    ) -> Batch:
        """按标识或最新完成批次选择待撤销的 forward 批次。"""
        if batch_id is None:
            batch = ledger.latest_forward_completed()
            if batch is None:
                raise ApplicationError("没有可撤销的批次")
            return batch
        batch = self._require_batch(ledger, batch_id)
        if batch.direction != "forward":
            raise ApplicationError(f"批次已经撤销：{batch.short_id}")
        return batch

    def _redo_target(
        self,
        ledger: Ledger,
        batch_id: str | None,
    ) -> Batch:
        """按标识或 redo 栈顶选择待重做的 backward 批次。"""
        if batch_id is None:
            batch = ledger.redo_target()
            if batch is None:
                raise ApplicationError("没有可重做的批次")
            return batch
        batch = self._require_batch(ledger, batch_id)
        if batch.direction != "backward":
            raise ApplicationError(f"批次尚未撤销：{batch.short_id}")
        if batch.id not in ledger.redo_stack:
            raise ApplicationError(
                f"批次已撤销但不可重做：{batch.short_id}；新的改名会作废更早的重做记录"
            )
        return batch

    @staticmethod
    def _require_batch(ledger: Ledger, batch_id: str) -> Batch:
        """按标识查找批次，不存在时转换为应用错误。"""
        try:
            return ledger.find(batch_id)
        except ValueError as exc:
            raise ApplicationError(str(exc)) from exc

    def _prepare(self, batch: Batch) -> Batch:
        """为可执行成员生成并登记同目录临时路径。"""
        reserved = {
            self._filesystem.key(path)
            for change in batch.changes
            if change.can_move
            for path in (change.source, change.target)
            if path is not None
        }
        changes = []
        for change in batch.changes:
            if not change.can_move:
                changes.append(change)
                continue
            while True:
                candidate = change.source.with_name(f".sr-{uuid4().hex}.tmp")
                key = self._filesystem.key(candidate)
                if key not in reserved and not self._filesystem.exists(candidate):
                    reserved.add(key)
                    break
            changes.append(replace(change, temporary=candidate, error=None))
        return replace(batch, changes=tuple(changes))

    def _excluded_temporaries(self, directory: Path, ledger: Ledger) -> set[Path]:
        """只排除当前目录内仍然存在的临时文件。"""
        return {
            path
            for path in ledger.temporary_paths()
            if path.is_relative_to(directory) and self._filesystem.exists(path)
        }

    @staticmethod
    def _filter_directory(directory: Path | str | None) -> Path | None:
        """解析可选目录；查询历史不要求目录仍存在。"""
        return None if directory is None else Path(directory).expanduser().resolve()

    @staticmethod
    def _now() -> datetime:
        """返回当前 UTC 时间。"""
        return datetime.now(timezone.utc)
