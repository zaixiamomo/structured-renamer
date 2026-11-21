"""执行前的目标名与冲突检查。"""

import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from sr.app.models import FileStamp
from sr.app.protocols import FileSystem


def check_moves(
    filesystem: FileSystem,
    moves: Iterable[tuple[Path, Path | None, FileStamp]],
    *,
    check_names: bool = True,
) -> dict[int, Exception]:
    """检查改名成员的目标名、文件变化和冲突。

    Args:
        filesystem: 文件系统访问端口。
        moves: (source, target, stamp) 序列；target 必须位于源文件所在目录。
        check_names: 是否按 Windows 规则校验目标文件名。
    Returns:
        以成员序号为键的错误映射；空映射表示可以执行。
    """
    moves = tuple(moves)
    errors, sources, targets = {}, {}, {}
    # 先独立校验每项，后续冲突检查只处理没有基础错误的成员。
    for i, (source, target, stamp) in enumerate(moves):
        try:
            if filesystem.stat(source) != stamp:
                raise ValueError("预览后源文件已变化，请重新准备")
            if target is None or target.parent != source.parent:
                raise ValueError("目标必须在源文件所在目录")
            if check_names:
                _validate_name(target.name)
            sources[i] = filesystem.key(source)
            targets[i] = filesystem.key(target)
        except (OSError, ValueError) as exc:
            errors[i] = exc
    # 统计本批源和目标键，用于发现重复入口和重复目标。
    source_counts, target_counts = (
        Counter(sources.values()),
        Counter(targets.values()),
    )
    for i, key in targets.items():
        try:
            if source_counts[sources[i]] > 1:
                raise ValueError("源文件入口重复")
            if target_counts[key] > 1:
                raise ValueError("多个文件生成相同目标名")
            # 目标被占用时，只有它同时是本批源文件才可能在链式改名中让出。
            if filesystem.exists(moves[i][1]) and key not in source_counts:
                raise FileExistsError(f"目标已被占用：{moves[i][1]}")
        except (OSError, ValueError) as exc:
            errors[i] = exc
    # 移除受阻项会缩小 available，重复检查直到不再产生新阻塞。
    while True:
        available = {key for i, key in sources.items() if i not in errors}
        blocked = {}
        for i, key in targets.items():
            if i in errors:
                continue
            try:
                if filesystem.exists(moves[i][1]) and key not in available:
                    raise FileExistsError(f"目标已被占用：{moves[i][1]}")
            except (OSError, ValueError) as exc:
                blocked[i] = exc
        if not blocked:
            break
        errors.update(blocked)
    return errors


def _validate_name(name: str) -> None:
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
