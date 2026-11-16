"""六边形端口协议，不依赖任何具体实现"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from renamer.core.model.issue import Issue
from renamer.core.model.undo import UndoRecord

__all__ = [
    "Clock",
    "FileSystem",
    "HttpClient",
    "Logger",
    "UndoLog",
    "is_case_only_change",
]


def is_case_only_change(src: Path, dst: Path) -> bool:
    """是否仅大小写不同的改名：同目录且名字大小写折叠相等但拼写不同

    预览冲突判定与文件系统改名共用这一策略：目标存在但仅为源的大小写变体时，
    视为同一文件（大小写两步改名），不算冲突。
    """
    return (
        src.parent == dst.parent
        and src.name != dst.name
        and src.name.casefold() == dst.name.casefold()
    )


class FileSystem(Protocol):
    """文件系统改名端口"""

    def rename(self, src: Path, dst: Path) -> None: ...

    def exists(self, path: Path) -> bool: ...


class HttpClient(Protocol):
    """网络抓取端口（GET/POST JSON）"""

    def get_json(
        self,
        url: str,
        *,
        method: str = "GET",
        payload: Mapping[str, object] | None = None,
    ) -> tuple[dict | None, Issue | None]: ...


class Clock(Protocol):
    """时间端口"""

    def __call__(self) -> float: ...


class Logger(Protocol):
    """结构化日志端口"""

    def log(self, event: dict) -> None: ...


class UndoLog(Protocol):
    """撤销日志端口"""

    def append(self, log_id: str, old: str, new: str) -> UndoRecord: ...

    def cancel(self, log_id: str, old: str, new: str) -> UndoRecord: ...

    def undo(self, log_id: str | None = None) -> list[UndoRecord]: ...

    def rename_records(self, log_id: str) -> list[UndoRecord]: ...
