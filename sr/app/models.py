"""改名批次、逐文件改动、文件快照与账本。"""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Literal

from sr.core.errors import FileError

Direction = Literal["forward", "backward"]
Status = Literal["running", "completed"]

# 核心不暴露未匹配文案，这里按既有消息识别跳过项，避免改动 core。
NO_MATCH_MESSAGE = "未匹配任何规则"

SHORT_ID_LENGTH = 8


class StoredError(Exception):
    """从状态文件恢复的错误。"""

    def __init__(
        self,
        type_name: str,
        message: str,
        *,
        stage: str | None = None,
        cause_type: str | None = None,
    ) -> None:
        """保存原始异常类型名称、消息和可选的文件错误信息。"""
        self.type_name = type_name
        self.stage = stage
        self.cause_type = cause_type
        super().__init__(message)

    @classmethod
    def from_error(cls, error: Exception) -> "StoredError":
        """把任意执行错误归一为可序列化的状态错误。"""
        if isinstance(error, cls):
            return error
        if isinstance(error, FileError):
            return cls(
                type(error).__name__,
                str(error),
                stage=error.stage,
                cause_type=type(error.cause).__name__,
            )
        return cls(type(error).__name__, str(error))


@dataclass(frozen=True)
class FileStamp:
    """文件与父目录身份、大小和修改时间的快照。"""

    parent: tuple[int, int]
    file: tuple[int, int]
    size: int
    modified_ns: int

    def __post_init__(self) -> None:
        """把身份信息规范为元组。"""
        object.__setattr__(self, "parent", tuple(self.parent))
        object.__setattr__(self, "file", tuple(self.file))


@dataclass(frozen=True)
class Change:
    """单个文件的计划、临时路径与错误。"""

    source: Path
    target: Path | None
    temporary: Path | None
    stamp: FileStamp
    error: Exception | None = None

    def __post_init__(self) -> None:
        """校验源、目标和临时路径都在同一目录。"""
        validate_paths(self.source.parent, (self.source,))
        if self.target is not None:
            validate_paths(self.source.parent, (self.source, self.target))
            if self.target.parent != self.source.parent:
                raise ValueError("只允许同目录改名")
        if self.temporary is not None:
            validate_paths(self.source.parent, (self.temporary,))
            if self.temporary.parent != self.source.parent:
                raise ValueError("临时路径必须在源文件所在目录")

    @property
    def can_move(self) -> bool:
        """判断成员是否无错误且需要改变文件名。"""
        return (
            self.error is None
            and self.target is not None
            and str(self.source) != str(self.target)
        )

    @property
    def ready(self) -> bool:
        """判断待改名成员是否已分配临时路径。"""
        return self.can_move and self.temporary is not None

    @property
    def prepared(self) -> bool:
        """判断成员是否已分配临时路径、进入执行阶段。"""
        return self.temporary is not None

    @property
    def unmatched(self) -> bool:
        """判断成员是否因未匹配任何规则而跳过。"""
        error = self.error
        if not isinstance(error, (FileError, StoredError)):
            return False
        return NO_MATCH_MESSAGE in str(error)

    @property
    def failed(self) -> bool:
        """判断成员是否为实际失败而不是跳过。"""
        return self.error is not None and not self.unmatched

    @property
    def unchanged(self) -> bool:
        """判断成员是否渲染出与原文件名相同的名字。"""
        return (
            self.error is None
            and self.target is not None
            and str(self.source) == str(self.target)
        )

    def endpoints(self, direction: Direction) -> tuple[Path, Path]:
        """按方向返回实际起点和终点。

        Args:
            direction: forward 返回源到目标，backward 返回目标到源。
        Returns:
            起点和终点路径。
        Raises:
            ValueError: 成员没有目标名。
        """
        if self.target is None:
            raise ValueError("没有目标名")
        if direction == "forward":
            return self.source, self.target
        return self.target, self.source


@dataclass(frozen=True)
class BatchCounts:
    """批次中成功、失败和跳过的文件数量。"""

    success: int
    failed: int
    skipped: int


@dataclass(frozen=True)
class Batch:
    """一次 rename、undo 或 redo 尝试的完整状态。"""

    id: str
    dir: Path
    direction: Direction
    status: Status
    updated: datetime
    changes: tuple[Change, ...]

    def __post_init__(self) -> None:
        """校验标识、方向、状态、时间和成员路径。"""
        object.__setattr__(self, "changes", tuple(self.changes))
        if not self.id:
            raise ValueError("批次必须有标识")
        if self.direction not in ("forward", "backward"):
            raise ValueError("未知批次方向")
        if self.status not in ("running", "completed"):
            raise ValueError("未知批次状态")
        if self.updated.tzinfo is None or self.updated.utcoffset() is None:
            raise ValueError("批次时间必须包含时区")
        validate_paths(
            self.dir,
            (
                path
                for change in self.changes
                for path in (change.source, change.target)
                if path is not None
            ),
        )

    @property
    def short_id(self) -> str:
        """返回用于展示和输入的短标识。"""
        return self.id[:SHORT_ID_LENGTH]

    @property
    def has_errors(self) -> bool:
        """判断批次是否包含逐文件错误。"""
        return any(change.error is not None for change in self.changes)

    def counts(self, *, replay: bool = False) -> BatchCounts:
        """按成功、失败和跳过统计成员。

        Args:
            replay: 为 True 时只统计进入执行阶段的成员，其余记作跳过。
        Returns:
            三类数量之和等于批次成员总数。
        """
        success = failed = skipped = 0
        for change in self.changes:
            if (replay and not change.prepared) or change.unmatched:
                skipped += 1
            elif change.failed:
                failed += 1
            elif change.can_move:
                success += 1
            else:
                skipped += 1
        return BatchCounts(success, failed, skipped)

    @property
    def movable(self) -> tuple[Change, ...]:
        """按原顺序返回无错误且需要改名的成员。"""
        return tuple(change for change in self.changes if change.can_move)

    @property
    def ready(self) -> tuple[Change, ...]:
        """按原顺序返回已分配临时路径的待改名成员。"""
        return tuple(change for change in self.changes if change.ready)


@dataclass(frozen=True)
class HistoryEntry:
    """历史中的批次及其当前是否可重做。"""

    batch: Batch
    redoable: bool


@dataclass(frozen=True)
class Ledger:
    """全局账本中的全部批次与 redo 栈。"""

    batches: tuple[Batch, ...] = ()
    redo_stack: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """校验批次标识、redo 栈和未完成批次约束。"""
        object.__setattr__(self, "batches", tuple(self.batches))
        object.__setattr__(self, "redo_stack", tuple(self.redo_stack))
        ids = [batch.id for batch in self.batches]
        if len(ids) != len(set(ids)):
            raise ValueError("批次标识重复")
        if len(self.redo_stack) != len(set(self.redo_stack)):
            raise ValueError("redo 栈重复")
        running = [batch for batch in self.batches if batch.status == "running"]
        if len(running) > 1:
            raise ValueError("同时只能有一个未完成批次")
        by_id = {batch.id: batch for batch in self.batches}
        for batch_id in self.redo_stack:
            batch = by_id.get(batch_id)
            if batch is None:
                raise ValueError("redo 栈引用了不存在的批次")
            # redo 开始后批次会成为 forward running，成功后从栈中移除。
            if not (
                (batch.direction == "backward" and batch.status == "completed")
                or (batch.direction == "forward" and batch.status == "running")
            ):
                raise ValueError("redo 栈引用了不可重做的批次")

    def find(self, batch_id: str) -> Batch:
        """按完整标识或唯一前缀查找批次。

        Args:
            batch_id: 完整标识或不产生歧义的前缀。
        Returns:
            唯一匹配的批次；完整标识优先。
        Raises:
            ValueError: 标识为空、不存在或前缀匹配多个批次。
        """
        if not batch_id:
            raise ValueError("批次标识不能为空")
        prefix = batch_id.lower()
        for batch in self.batches:
            if batch.id.lower() == prefix:
                return batch
        matches = [
            batch for batch in self.batches if batch.id.lower().startswith(prefix)
        ]
        if not matches:
            raise ValueError(f"批次不存在：{batch_id}")
        if len(matches) > 1:
            candidates = "、".join(
                f"{batch.short_id}（{batch.dir}）" for batch in matches
            )
            raise ValueError(f"批次前缀不唯一：{batch_id}；候选：{candidates}")
        return matches[0]

    def with_batch(self, batch: Batch) -> "Ledger":
        """替换同标识批次；不存在时追加。

        Args:
            batch: 待写入的批次快照。
        Returns:
            保留其他批次顺序的新账本。
        Raises:
            ValueError: 更新后违反账本或 redo 栈约束。
        """
        found = False
        batches: list[Batch] = []
        for current in self.batches:
            if current.id == batch.id:
                batches.append(batch)
                found = True
            else:
                batches.append(current)
        if not found:
            batches.append(batch)
        return replace(self, batches=tuple(batches))

    def running(self) -> Batch | None:
        """返回唯一的未完成批次；不存在时返回 None。"""
        return next(
            (batch for batch in self.batches if batch.status == "running"),
            None,
        )

    def latest_forward_completed(self) -> Batch | None:
        """返回最新完成的正向批次。

        Returns:
            按更新时间选择的批次，同时间取账本中靠后的项；无匹配时为 None。
        """
        candidates = [
            (index, batch)
            for index, batch in enumerate(self.batches)
            if batch.direction == "forward" and batch.status == "completed"
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: (item[1].updated, item[0]))[1]

    def redo_target(self) -> Batch | None:
        """返回 redo 栈顶批次。

        Returns:
            最近压栈的批次；栈为空时为 None。
        """
        return self.find(self.redo_stack[-1]) if self.redo_stack else None

    def clear_redo(self) -> "Ledger":
        """返回清空 redo 栈后的账本。"""
        return replace(self, redo_stack=())

    def push_redo(self, batch_id: str) -> "Ledger":
        """把批次压入 redo 栈，去重后放到栈顶。"""
        stack = tuple(item for item in self.redo_stack if item != batch_id)
        return replace(self, redo_stack=(*stack, batch_id))

    def remove_redo(self, batch_id: str) -> "Ledger":
        """返回从 redo 栈移除指定标识后的账本。"""
        return replace(
            self,
            redo_stack=tuple(item for item in self.redo_stack if item != batch_id),
        )

    def settle(self, batch: Batch) -> "Ledger":
        """结算批次并维护 redo 栈。

        Args:
            batch: 本次执行或恢复后的批次快照。
        Returns:
            反向完成时压栈、反向未完成或正向完成时移出栈的新账本。
        Raises:
            ValueError: 更新后违反账本或 redo 栈约束。
        """
        if (batch.direction == "backward" and batch.status == "running") or (
            batch.direction == "forward" and batch.status == "completed"
        ):
            # 先移出栈，避免反向恢复未完成时构造出违反 redo 约束的账本。
            return self.remove_redo(batch.id).with_batch(batch)
        settled = self.with_batch(batch)
        if batch.status == "completed":
            return settled.push_redo(batch.id)
        return settled

    def temporary_paths(self) -> tuple[Path, ...]:
        """按批次和成员顺序返回账本记录的全部临时路径。"""
        return tuple(
            change.temporary
            for batch in self.batches
            for change in batch.changes
            if change.temporary is not None
        )


def validate_paths(directory: Path, paths: Iterable[Path | None]) -> None:
    """校验目录与成员路径都在根目录内且不含父级引用。

    Args:
        directory: 操作根目录，必须是规范绝对路径。
        paths: 待校验的文件或临时路径。
    Raises:
        ValueError: 目录或成员路径越界、包含父级引用。
    """
    if not directory.is_absolute() or ".." in directory.parts:
        raise ValueError("目录必须是规范绝对路径")
    if any(
        path is not None
        and (
            not path.is_absolute()
            or ".." in path.parts
            or not path.is_relative_to(directory)
        )
        for path in paths
    ):
        raise ValueError("文件路径越出操作目录")
