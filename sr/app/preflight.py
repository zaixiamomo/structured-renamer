"""执行前的源状态、名称合法性与批内冲突检查。"""

import re
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

from sr.app.models import Batch, Change, Direction
from sr.app.protocols import FileSystem


@dataclass(frozen=True)
class _Checked:
    """单个成员通过基础校验后的端点与比较键。"""

    end: Path
    source_key: tuple[int, int, str]
    target_key: tuple[int, int, str]


class RenamePreflight:
    """执行前逐项检查批次并写回错误。"""

    def __init__(self, filesystem: FileSystem) -> None:
        """保存执行前检查使用的文件系统端口。"""
        self._filesystem = filesystem

    def check(self, batch: Batch, *, check_names: bool = True) -> Batch:
        """给批次中的可执行成员逐项标记错误。

        Args:
            batch: 待检查批次。
            check_names: 是否按 Windows 规则校验目标文件名；撤销恢复原名时关闭。
        Returns:
            新的 Batch；错误已写回对应 Change，其他成员保持原样。
        """
        changes = list(batch.changes)
        errors: list[Exception | None] = [change.error for change in changes]
        checked = self._check_items(changes, errors, batch.direction, check_names)
        self._check_conflicts(errors, checked)
        marked = tuple(
            change if change.error is error else replace(change, error=error)
            for change, error in zip(changes, errors)
        )
        return replace(batch, changes=marked)

    def _check_items(
        self,
        changes: list[Change],
        errors: list[Exception | None],
        direction: Direction,
        check_names: bool,
    ) -> dict[int, _Checked]:
        """逐项校验源快照、目录和名称，返回通过的端点与键。"""
        checked: dict[int, _Checked] = {}
        for index, change in enumerate(changes):
            if change.error is not None:
                continue
            if change.target is None:
                errors[index] = ValueError("没有目标名")
                continue
            if not change.can_move:
                continue
            start, end = change.endpoints(direction)
            try:
                if self._filesystem.stat(start) != change.stamp:
                    raise ValueError("预览后源文件已变化，请重新准备")
                if end.parent != start.parent:
                    raise ValueError("目标必须在源文件所在目录")
                if check_names:
                    self._validate_name(end.name)
                checked[index] = _Checked(
                    end=end,
                    source_key=self._filesystem.key(start),
                    target_key=self._filesystem.key(end),
                )
            except (OSError, ValueError) as exc:
                errors[index] = exc
        return checked

    def _check_conflicts(
        self, errors: list[Exception | None], checked: dict[int, _Checked]
    ) -> None:
        """标记重复入口、重复目标和被占用的目标，并传播由此产生的阻塞。"""
        source_counts = Counter(item.source_key for item in checked.values())
        target_counts = Counter(item.target_key for item in checked.values())
        for index, item in checked.items():
            try:
                if source_counts[item.source_key] > 1:
                    raise ValueError("源文件入口重复")
                if target_counts[item.target_key] > 1:
                    raise ValueError("多个文件生成相同目标名")
            except ValueError as exc:
                errors[index] = exc

        # 标记受阻项会缩小可用源名字，可能再堵住别人，循环到不再有新阻塞。
        while True:
            available = {
                item.source_key
                for index, item in checked.items()
                if errors[index] is None
            }
            blocked: dict[int, Exception] = {}
            for index, item in checked.items():
                if errors[index] is not None:
                    continue
                try:
                    if (
                        self._filesystem.exists(item.end)
                        and item.target_key not in available
                    ):
                        raise FileExistsError(f"目标已被占用：{item.end}")
                except (OSError, ValueError) as exc:
                    blocked[index] = exc
            if not blocked:
                break
            for index, error in blocked.items():
                errors[index] = error

    def _validate_name(self, name: str) -> None:
        """按 Windows 文件名规则校验目标名。"""
        if (
            not name
            or name in {".", ".."}
            or name.endswith((".", " "))
            or any(char in '<>:"/\\|?*' or ord(char) < 32 for char in name)
            # 保留设备名及其带扩展名形式；¹²³ 是 COM/LPT 的兼容上标。
            or re.fullmatch(
                r"(?i:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])", name.split(".")[0]
            )
            or len(name.encode("utf-16-le")) // 2 > 255
            or len(name.encode("utf-8")) > 255
        ):
            raise ValueError(f"非法目标文件名：{name!r}")
