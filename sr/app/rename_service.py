"""应用服务：准备、执行和撤销改名。"""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

from sr.app.errors import ApplicationError
from sr.app.models import (
    DirectoryState,
    ExecutionReport,
    PlanItem,
    RenameOperation,
    RenamePlan,
)
from sr.app.preflight import check_moves
from sr.app.protocols import FileSystem, RuleCodec, StateStore
from sr.app.rename_executor import RenameExecutor
from sr.core.compile.rule import Rule
from sr.core.run import run_compiled
from sr.core.runtime.state import FileState
from sr.plugin import ExtenderResources, PluginCatalog


class RenameService:
    """编排规则编译、预览、执行和撤销。"""

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
        """创建服务。

        Args:
            filesystem: 文件系统端口。
            codec: 规则编解码端口。
            store: 状态存储端口。
            catalog: 插件能力目录；省略时使用空目录。
            resources: 拓展资源；省略时使用无资源集合。
            max_workers: 分组求值线程数，必须是正整数。
        Raises:
            ValueError: max_workers 不是正整数。
        """
        if type(max_workers) is not int or max_workers < 1:
            raise ValueError("max_workers 必须是正整数")
        self._max_workers = max_workers
        self._filesystem = filesystem
        self._executor = RenameExecutor(filesystem)
        self._codec = codec
        self._store = store
        self._catalog = PluginCatalog() if catalog is None else catalog
        self._resources = ExtenderResources() if resources is None else resources

    def _directory(self, directory: Path | str) -> Path:
        """解析并校验待处理目录。"""
        return self._filesystem.resolve(Path(directory).expanduser().absolute())

    def inspect(self, directory: Path | str) -> DirectoryState:
        """读取目录的持久化状态。

        Args:
            directory: 待查询目录。
        Returns:
            DirectoryState；无记录时为空状态。
        Raises:
            ApplicationError: 状态文件损坏或版本不兼容。
        """
        directory = self._directory(directory)
        with self._store.lock(directory):
            return self._store.load(directory)

    def prepare(
        self,
        directory: Path | str,
        rule: Rule | Path | str,
        *,
        files: Sequence[Path | str] | None = None,
    ) -> RenamePlan:
        """计算一次改名计划。

        规则文件读取或解析失败时直接传播底层异常。

        Args:
            directory: 待处理目录。
            rule: Rule 对象，或 YAML 规则文件路径。
            files: 可选的待处理文件子集；相对路径按 directory 解析。
        Returns:
            包含逐文件目标或错误的 RenamePlan。
        Raises:
            ApplicationError: 目录有未完成操作、所选文件无效或路径无法区分。
        """
        directory = self._directory(directory)
        with self._store.lock(directory):
            # 有未完成操作时拒绝重新准备，避免覆盖可恢复状态。
            self._store.load(directory).check()
            excluded = ()
            if not isinstance(rule, Rule):
                rule_path = Path(rule).expanduser().absolute()
                rule = self._codec.decode(self._filesystem.read(rule_path))
                # 规则文件本身不参与扫描，避免被当作待改名文件。
                excluded += (rule_path,)
            available = self._filesystem.scan(directory, excluded)
            paths = (
                available
                if files is None
                else self._select(directory, available, files)
            )
            # WindowsPath 判等忽略大小写，重复快照意味着核心无法区分这些文件。
            snapshots = {path: self._filesystem.stat(path) for path in paths}
            if len(snapshots) != len(paths):
                raise ApplicationError("当前核心路径映射无法区分这些文件的大小写")
            results = self._evaluate(paths, rule)
            items = []
            for path, result in results.items():
                target, error = None, result.error
                if error is None:
                    try:
                        if result.result is None:
                            raise ValueError("核心未返回名称主体")
                        # 核心只生成名称主体，原后缀统一保留。
                        target = path.with_name(result.result + path.suffix)
                    except ValueError as exc:
                        error = exc
                items.append(PlanItem(path, target, snapshots[path], error))
            # 对可执行成员做目标名校验和冲突检查。
            ready = [i for i, item in enumerate(items) if item.error is None]
            errors = check_moves(
                self._filesystem,
                ((items[i].source, items[i].target, items[i].stamp) for i in ready),
            )
            for index, error in errors.items():
                i = ready[index]
                items[i] = replace(items[i], error=error)
            return RenamePlan(directory, tuple(items))

    def _evaluate(
        self, paths: tuple[Path, ...], rule: Rule
    ) -> Mapping[Path, FileState]:
        """编译规则、创建所需拓展并运行核心管线。"""
        compiled = rule.compile(extenders=self._catalog.extenders)
        required = (
            node.name for producers in compiled.producers.values() for node in producers
        )
        extenders = self._catalog.create_batch(required, self._resources)
        return run_compiled(
            paths, (compiled,), extenders=extenders, max_workers=self._max_workers
        )

    def execute(self, plan: RenamePlan) -> ExecutionReport:
        """执行计划。

        执行前会重新校验文件；失败时直接抛出对应成员错误。

        Args:
            plan: prepare 返回的计划。
        Returns:
            执行报告；计划为空时返回前后相同且无改名的报告。
        Raises:
            ApplicationError: 目录已有未完成操作。
            StateWriteError: 保存执行进度失败，操作已停止。
        """
        with self._store.lock(plan.directory):
            state = self._store.load(plan.directory)
            state.check()
            operation = plan.materialize()
            errors = check_moves(
                self._filesystem,
                ((c.source, c.target, c.stamp) for c in plan.items if c.error is None),
            )
            if errors:
                # 按成员序号抛出最靠前的错误，便于定位。
                raise errors[min(errors)]
            if not operation.changes:
                return ExecutionReport(operation, operation)
            state = state.start(operation)
            self._store.save(state)
            return self._run_operation(state)

    def undo(self, directory: Path | str) -> ExecutionReport:
        """恢复未完成操作，或撤销上一批已完成的改名。

        存在 active 时先对账再恢复，否则由 undo 记录构造反向操作。

        Args:
            directory: 目标目录。
        Returns:
            与 execute 相同结构的执行报告。
        Raises:
            ApplicationError: 没有可撤销记录，或当前状态不允许撤销。
            StateWriteError: 保存执行进度失败，操作已停止。
        """
        directory = self._directory(directory)
        with self._store.lock(directory):
            state = self._store.load(directory)
            restoring = state.active is not None
            operation = (
                self._executor.reconcile(state.active) if restoring else state.reverse()
            )
            errors = check_moves(
                self._filesystem,
                (
                    (c.actual_path, c.source if restoring else c.target, c.stamp)
                    for c in operation.changes
                ),
                # 撤销回到原文件名，不再按新文件规则校验目标名。
                check_names=False,
            )
            if errors:
                raise errors[min(errors)]
            state = (
                replace(state, active=operation)
                if restoring
                else state.start(operation)
            )
            self._store.save(state)
            return self._run_operation(state, restoring=restoring)

    def _select(
        self,
        directory: Path,
        available: Sequence[Path],
        selected: Sequence[Path | str],
    ) -> tuple[Path, ...]:
        """把用户选择解析为目录内已扫描的文件。"""
        by_key = {self._filesystem.key(path): path for path in available}
        paths, seen = [], set()
        for value in selected:
            # 选择项可以是相对目录或绝对路径，最终必须命中扫描结果。
            path = Path(value).expanduser()
            path = path if path.is_absolute() else directory / path
            try:
                key = self._filesystem.key(path)
                member = by_key[key]
            except (OSError, ValueError, KeyError) as exc:
                raise ApplicationError(
                    f"所选路径不是目录内可处理的普通文件：{path}"
                ) from exc
            if key in seen:
                raise ApplicationError(f"重复选择同一文件入口：{path}")
            seen.add(key)
            paths.append(member)
        return tuple(paths)

    def _run_operation(
        self, state: DirectoryState, *, restoring: bool = False
    ) -> ExecutionReport:
        """执行操作并结算目录状态。"""
        if state.active is None:
            raise ApplicationError("没有待执行的操作")

        def _checkpoint(progress: RenameOperation) -> None:
            """把当前进度写回状态存储。"""
            # 每次进度都写回状态，进程中断后可由 undo 对账。
            self._store.save(replace(state, active=progress))

        report = self._executor.execute(
            state.active, checkpoint=_checkpoint, restoring=restoring
        )
        self._store.save(state.finish(report, restoring=restoring))
        return report
