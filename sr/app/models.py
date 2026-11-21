"""改名计划、操作和目录状态的不可变模型。"""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from sr.app.errors import ApplicationError


@dataclass(frozen=True)
class FileStamp:
    """用于检测文件变化的元数据快照。"""

    # parent/file 为 (设备号, inode)，区分同名和替换后的文件。
    parent: tuple[int, int]
    file: tuple[int, int]
    size: int
    modified_ns: int

    def __post_init__(self) -> None:
        """把身份信息规范为元组。"""
        object.__setattr__(self, "parent", tuple(self.parent))
        object.__setattr__(self, "file", tuple(self.file))


@dataclass(frozen=True)
class PlanItem:
    """计划中的一个源文件及其目标或错误。"""

    source: Path
    target: Path | None
    stamp: FileStamp
    error: Exception | None = None


@dataclass(frozen=True)
class RenamePlan:
    """一次预览得到的改名计划。"""

    directory: Path
    items: tuple[PlanItem, ...]

    def __post_init__(self) -> None:
        """校验目录与成员路径，并冻结成员。"""
        object.__setattr__(self, "items", tuple(self.items))
        _validate_paths(
            self.directory,
            (path for item in self.items for path in (item.source, item.target)),
        )

    def materialize(self) -> "RenameOperation":
        """把无错误的计划成员转换为执行操作。

        Returns:
            kind="execute" 的 RenameOperation，只包含源与目标不同的成员。
        Raises:
            ValueError: 可执行成员缺少目标。
        """
        for item in self.items:
            if item.error is not None:
                continue
            if item.target is None:
                raise ValueError("计划成员缺少目标")
        return RenameOperation(
            "execute",
            tuple(
                FileChange(item.source, item.target, item.source, item.stamp)
                for item in self.items
                if item.error is None and str(item.source) != str(item.target)
            ),
        )


@dataclass(frozen=True)
class FileChange:
    """单文件改名成员。"""

    source: Path
    target: Path
    # actual_path 是当前已确认的位置，执行中可能介于 source 和 target 之间。
    actual_path: Path
    stamp: FileStamp

    def __post_init__(self) -> None:
        """校验目标位置与源文件同目录。"""
        if not isinstance(self.target, Path):
            raise TypeError("操作成员必须有目标路径")
        if (
            self.target.parent != self.source.parent
            or self.actual_path.parent != self.source.parent
        ):
            raise ValueError("操作成员的目标和实际位置必须在源文件所在目录")


@dataclass(frozen=True)
class MoveIntent:
    """已登记但尚未确认的文件移动。"""

    index: int
    target: Path


@dataclass(frozen=True)
class RenameOperation:
    """一次执行或撤销的不可变改名操作。"""

    kind: Literal["execute", "undo"]
    changes: tuple[FileChange, ...]
    pending: MoveIntent | None = None

    def __post_init__(self) -> None:
        """校验操作类型和 pending 位置。"""
        object.__setattr__(self, "changes", tuple(self.changes))
        if self.kind not in ("execute", "undo"):
            raise ValueError("未知操作类型")
        if self.pending is not None:
            if not 0 <= self.pending.index < len(self.changes):
                raise ValueError("未完成改名的成员序号无效")
            if (
                self.pending.target.parent
                != self.changes[self.pending.index].source.parent
            ):
                raise ValueError("未完成改名的目标必须在源文件所在目录")

    @property
    def initial(self) -> bool:
        """全部成员仍位于操作起点。"""
        return self.pending is None and all(
            str(change.actual_path) == str(change.source) for change in self.changes
        )

    @property
    def completed(self) -> bool:
        """全部成员已到达目标。"""
        return self.pending is None and all(
            str(change.actual_path) == str(change.target) for change in self.changes
        )

    def confirm(self, index: int, path: Path) -> "RenameOperation":
        """确认某成员已到达指定位置。

        Args:
            index: 成员在 changes 中的序号。
            path: 实际确认位置，必须在源文件所在目录。
        Returns:
            清除 pending 并更新 actual_path 的新操作。
        Raises:
            ValueError: 序号越界，或 path 不在源目录内。
        """
        if not 0 <= index < len(self.changes):
            raise ValueError("改名成员序号无效")
        changes = list(self.changes)
        changes[index] = replace(changes[index], actual_path=path)
        return replace(self, changes=tuple(changes), pending=None)

    def verify(self, other: "RenameOperation") -> None:
        """确认 other 与本操作对应同一组成员和同一来源戳。

        Args:
            other: 待核对的操作，允许 actual_path 和 pending 不同。
        Raises:
            ValueError: 操作类型、成员数量、源、目标或来源戳不一致。
        """
        if (
            self.kind != other.kind
            or len(self.changes) != len(other.changes)
            or any(
                (str(before.source), str(before.target), before.stamp)
                != (str(after.source), str(after.target), after.stamp)
                for before, after in zip(self.changes, other.changes)
            )
        ):
            raise ValueError("报告成员必须对应同一操作")


@dataclass(frozen=True)
class ExecutionReport:
    """一次执行前后的操作快照与错误。"""

    before: RenameOperation
    after: RenameOperation
    error: Exception | None = None
    recovery_errors: tuple[Exception, ...] = ()

    def __post_init__(self) -> None:
        """校验快照对应性并拒绝未确认位置。"""
        self.before.verify(self.after)
        if self.before.pending is not None or self.after.pending is not None:
            raise ValueError("报告只能使用已确认位置的操作快照")
        object.__setattr__(self, "recovery_errors", tuple(self.recovery_errors))

    @property
    def changed(self) -> tuple[FileChange, ...]:
        """返回实际位置发生变化的成员。"""
        return tuple(
            after
            for before, after in zip(self.before.changes, self.after.changes)
            if str(before.actual_path) != str(after.actual_path)
        )


@dataclass(frozen=True)
class DirectoryState:
    """单个目录的持久化改名状态。"""

    directory: Path
    undo: tuple[FileChange, ...] = ()
    active: RenameOperation | None = None

    def __post_init__(self) -> None:
        """校验撤销记录、活动操作和路径边界。"""
        object.__setattr__(self, "undo", tuple(self.undo))
        for change in self.undo:
            if str(change.actual_path) != str(change.target) or str(
                change.source
            ) == str(change.actual_path):
                raise ValueError("撤销记录必须来自同目录已完成的实际改名")
        if self.active is not None and self.active.kind == "undo":
            # 撤销操作必须与 undo 记录逐项对应（源、目标互换且 stamp 不变）。
            expected = tuple(
                (str(c.actual_path), str(c.source), c.stamp) for c in self.undo
            )
            actual = tuple(
                (str(c.source), str(c.target), c.stamp) for c in self.active.changes
            )
            if not self.undo or actual != expected:
                raise ValueError("撤销操作与原始记录不对应")
        changes = (*self.undo, *(self.active.changes if self.active else ()))
        paths = [
            path
            for change in changes
            for path in (change.source, change.target, change.actual_path)
        ]
        if self.active is not None and self.active.pending is not None:
            paths.append(self.active.pending.target)
        _validate_paths(self.directory, paths)

    @property
    def undoable(self) -> bool:
        """存在进行中操作或可撤销记录。"""
        return self.active is not None or bool(self.undo)

    def check(self) -> None:
        """确认当前目录没有未完成操作。

        Raises:
            ApplicationError: 需要先执行 --undo 恢复。
        """
        if self.active is not None:
            raise ApplicationError("上次操作尚未完成，请先 --undo 恢复")

    def start(self, operation: RenameOperation) -> "DirectoryState":
        """登记新的操作。

        Args:
            operation: 必须从已确认的原始位置开始。
        Returns:
            active 指向新状态的新 DirectoryState。
        Raises:
            ApplicationError: 已有未完成操作。
            ValueError: 操作不在初始位置。
        """
        self.check()
        if not operation.initial:
            raise ValueError("新操作必须从已确认的原始位置开始")
        return replace(self, active=operation)

    def reverse(self) -> RenameOperation:
        """由 undo 记录构造反向操作。

        Returns:
            目标与源互换的 kind="undo" 操作。
        Raises:
            ApplicationError: 没有可撤销记录或仍有未完成操作。
        """
        self.check()
        if not self.undo:
            raise ApplicationError("当前目录没有可撤销的改名")
        return RenameOperation(
            "undo",
            tuple(FileChange(c.target, c.source, c.target, c.stamp) for c in self.undo),
        )

    def finish(
        self, report: ExecutionReport, *, restoring: bool = False
    ) -> "DirectoryState":
        """用执行报告结算当前操作。

        Args:
            report: before/after 快照；before 必须对应当前确认位置。
            restoring: 是否正在恢复未完成操作。
        Returns:
            结算后的状态：成功执行时记录 undo；失败时保留非初始进度的
            active 供 --undo 恢复。
        Raises:
            ValueError: 报告与当前操作不一致，或成功/恢复的终点不完整。
        """
        operation = self.active
        if operation is None:
            raise ValueError("没有待结算的操作")
        operation.verify(report.before)
        if operation.pending is not None or any(
            str(current.actual_path) != str(before.actual_path)
            for current, before in zip(operation.changes, report.before.changes)
        ):
            raise ValueError("报告起点必须对应当前操作的确认位置")
        progress = report.after
        if report.error is not None:
            # 未移动任何文件且非恢复时直接清除 active；否则保留进度等待 --undo。
            return replace(
                self, active=progress if restoring or not progress.initial else None
            )
        if restoring:
            if not progress.initial:
                raise ValueError("恢复完成后所有成员必须回到操作起点")
            return replace(self, active=None)
        if not progress.completed:
            raise ValueError("成功报告中的成员必须到达目标")
        completed = tuple(c for c in progress.changes if str(c.source) != str(c.target))
        # 全为空操作的执行保留上一批 undo，避免无效操作清空撤销历史。
        records = (completed or self.undo) if operation.kind == "execute" else ()
        return replace(self, undo=records, active=None)


def _validate_paths(directory: Path, paths: Iterable[Path | None]) -> None:
    """拒绝相对目录、父级引用和越出目录的成员路径。"""
    if not directory.is_absolute() or ".." in directory.parts:
        raise ValueError("状态目录必须是规范绝对路径")
    if any(
        not path.is_absolute()
        or ".." in path.parts
        or not path.is_relative_to(directory)
        for path in paths
        if path is not None
    ):
        raise ValueError("状态中的文件路径越出目标目录")
