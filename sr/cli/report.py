"""把批次和历史格式化为文本，不访问文件系统或输出流。"""

import unicodedata
from pathlib import Path

from sr.app.models import Batch, Change, HistoryEntry, StoredError


def _paint(text: str, code: str, color: bool) -> str:
    """按需添加 ANSI 颜色，宽度计算始终使用原始文本。"""
    return f"\033[{code}m{text}\033[0m" if color else text


def _display_width(text: str) -> int:
    """按终端显示宽度计算文本列数。"""
    # 全角/宽字符占两列，组合标记和格式字符不占列。
    return sum(
        2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
        for char in text
        if unicodedata.category(char) not in ("Mn", "Me", "Cf")
    )


def _arrow(backward: bool, color: bool) -> str:
    """返回与操作方向一致的灰色箭头。"""
    return _paint("<-" if backward else "->", "90", color)


def _format_move(
    source: str,
    target: str,
    width: int,
    color: bool,
    *,
    backward: bool,
) -> str:
    """对齐旧名后追加箭头和结果名，结果名标绿。"""
    padding = " " * (width - _display_width(source))
    if backward:
        return f"{_paint(source, '32', color)}{padding}  {_arrow(backward, color)}  {target}"
    return (
        f"{source}{padding}  {_arrow(backward, color)}  {_paint(target, '32', color)}"
    )


def _format_error(error: Exception) -> str:
    """显示错误类型和消息。"""
    type_name = (
        error.type_name if isinstance(error, StoredError) else type(error).__name__
    )
    return f"{type_name}: {error}"


def _format_counts(batch: Batch, *, color: bool, replay: bool = False) -> str:
    """汇总文件总数，并按成功、失败、跳过输出非零项。"""
    counts = batch.counts(replay=replay)
    labeled = (
        ("成功", counts.success, "32"),
        ("失败", counts.failed, "31"),
        ("跳过", counts.skipped, "90"),
    )
    parts = [_paint(f"文件总数：{len(batch.changes)}", "34", color)]
    parts.extend(
        _paint(f"{label}：{value}", code, color)
        for label, value, code in labeled
        if value
    )
    return "  |  ".join(parts)


class _BatchTree:
    """按目录组织批次全部文件的文本树。"""

    def __init__(self, batch: Batch, *, color: bool, replay: bool) -> None:
        """按旧名建立目录和文件索引。"""
        self._batch = batch
        self._color = color
        self._replay = replay
        self._files: dict[Path, Change] = {}
        self._children: dict[Path, set[Path]] = {batch.dir: set()}
        for change in batch.changes:
            source = change.source
            self._files[source] = change
            self._children.setdefault(source.parent, set()).add(source)
            parent = source.parent
            while parent != batch.dir:
                self._children.setdefault(parent.parent, set()).add(parent)
                parent = parent.parent

    def format(self) -> str:
        """返回根路径、目录分支和全部文件行。"""
        lines = [_paint(str(self._batch.dir), "1;34", self._color)]
        pending: list[tuple[Path | None, str]] = [(self._batch.dir, "")]
        while pending:
            directory, prefix = pending.pop()
            if directory is None:
                lines.append(prefix)
                continue
            children = sorted(
                self._children[directory],
                key=lambda path: (path in self._files, path.name),
            )
            width = max(
                (
                    _display_width(path.name)
                    for path in children
                    if path in self._files and not self._gray(self._files[path])
                ),
                default=0,
            )
            # 反向压栈让目录和文件都按展示顺序展开，避免递归深度限制。
            entries = []
            for index, path in enumerate(children):
                last = index == len(children) - 1
                branch = "└── " if last else "├── "
                continuation = "    " if last else "│   "
                if path in self._files:
                    label = self._format_file(path, width)
                else:
                    label = _paint(path.name + "/", "1;34", self._color)
                line = _paint(prefix + branch, "90", self._color) + label
                entries.append((path, line, prefix + continuation))
            for path, line, continuation in reversed(entries):
                if path not in self._files:
                    pending.append((path, continuation))
                pending.append((None, line))
        return "\n".join(lines)

    def _untouched(self, change: Change) -> bool:
        """判断回放时该成员是否从未进入执行阶段。"""
        return self._replay and not change.prepared

    def _gray(self, change: Change) -> bool:
        """判断是否只显示灰色文件名。"""
        return change.unmatched or change.unchanged or self._untouched(change)

    def _format_gray(self, change: Change) -> str:
        """只显示灰色文件名。"""
        return _paint(change.source.name, "90", self._color)

    def _format_file(self, path: Path, width: int) -> str:
        """在文件名同行追加改名或错误，保留未改名文件。"""
        change = self._files[path]
        if self._gray(change):
            return self._format_gray(change)
        backward = self._batch.direction == "backward"
        if change.error is not None:
            error = " ".join(_format_error(change.error).splitlines())
            padding = " " * (width - _display_width(path.name))
            message = _paint(error, "31", self._color)
            arrow = _arrow(backward, self._color)
            return f"{path.name}{padding}  {arrow}  {message}"
        if change.can_move and change.target is not None:
            return _format_move(
                path.name,
                change.target.name,
                width,
                self._color,
                backward=backward,
            )
        return self._format_gray(change)


def format_batch(
    batch: Batch,
    *,
    color: bool = False,
    dry_run: bool = False,
    replay: bool = False,
) -> str:
    """把批次全部文件格式化为目录树，同行显示改名或错误。

    Args:
        batch: 待展示的批次；始终以旧名为起点，方向只决定箭头与高亮。
        color: 是否添加 ANSI 颜色。
        dry_run: 是否为预览；成功数量表示计划可改名的文件。
        replay: 是否为撤销或重做回放；未执行的文件显示为灰色且不计入统计。
    Returns:
        以批次目录为根、同目录内箭头对齐的文件树和结果提示。
    """
    lines = [_BatchTree(batch, color=color, replay=replay).format(), ""]
    if dry_run:
        lines.append(_paint("预览结果（未执行改名）", "33", color))
    lines.append(_format_counts(batch, color=color, replay=replay))
    if not dry_run and batch.status == "running":
        lines.append(
            _paint(
                "批次尚未完成；成功表示无错误的改名项，实际文件位置需恢复确认",
                "33",
                color,
            )
        )
    return "\n".join(lines)


def format_history(entries: tuple[HistoryEntry, ...], *, color: bool = False) -> str:
    """把批次历史格式化为单行摘要。

    Args:
        entries: 已按展示顺序排列的历史快照。
        color: 是否添加 ANSI 颜色。
    Returns:
        每个批次一行的状态、标识、时间和目录，字段以 | 分隔；无批次时返回提示。
    """
    lines = []
    for entry in entries:
        batch = entry.batch
        updated = batch.updated.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        if batch.status == "running":
            label, code = "未完成", "33"
        elif batch.direction == "backward":
            label = "可重做" if entry.redoable else "已撤销"
            code = "36" if entry.redoable else "90"
        else:
            label, code = "已完成", "32"
        status = _paint(label, code, color)
        lines.append(f"{status} | {batch.short_id} | {updated} | {batch.dir}")
    return "\n".join(lines) or _paint("没有历史记录", "33", color)


def format_unfinished(batch: Batch, *, color: bool = False) -> str:
    """格式化未完成批次的阻断提示。"""
    line = format_history((HistoryEntry(batch, False),), color=color)
    notice = _paint(
        "\n".join(
            (
                "检测到未完成的改名批次，已停止本次 run",
                "",
                f"查看详情：sr log --id {batch.short_id}",
                f"回滚旧名：sr undo --id {batch.short_id}",
                f"继续新名：sr redo --id {batch.short_id}",
            )
        ),
        "33",
        color,
    )
    return f"{line}\n{notice}"


def format_notice(message: str, *, color: bool = False) -> str:
    """把提示信息格式化为黄色文本。"""
    return _paint(message, "33", color)


def format_failure(message: str, *, color: bool = False) -> str:
    """把意外错误格式化为红色文本。"""
    return _paint(f"错误：{message}", "31", color)
