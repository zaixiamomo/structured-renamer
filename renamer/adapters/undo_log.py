"""撤销日志端口适配器：JSONL 追加式持久化与撤销"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path

from renamer.core.model import UndoRecord

from .filesystem import apply_rename

__all__ = ["UndoLog"]

_KIND_RENAME = "rename"
_KIND_UNDO = "undo"
_KIND_UNDONE = "undone"
_KIND_CANCEL = "cancel"


class UndoLog:
    """JSONL 追加式改名日志与撤销，满足 UndoLog 端口协议"""

    def __init__(
        self,
        path: Path | str,
        *,
        clock: Callable[[], float] | None = None,
        rename: Callable[[Path, Path], None] | None = None,
    ) -> None:
        self.path = Path(path)
        self._clock = clock or time.time
        self._rename = rename or os.rename

    def append(self, log_id: str, old: str, new: str) -> UndoRecord:
        """追加一条正向改名记录"""
        record = UndoRecord(
            log_id=log_id,
            old=old,
            new=new,
            ts=self._clock(),
            kind=_KIND_RENAME,
        )
        self._write_record(record)
        return record

    def cancel(self, log_id: str, old: str, new: str) -> UndoRecord:
        """追加一条抵消记录，使对应的正向改名记录失效"""
        record = UndoRecord(
            log_id=log_id,
            old=old,
            new=new,
            ts=self._clock(),
            kind=_KIND_CANCEL,
        )
        self._write_record(record)
        return record

    def undo(self, log_id: str | None = None) -> list[UndoRecord]:
        """撤销 log_id 的改名（默认最近一次），返回实际还原的记录，幂等"""
        all_records = self._records()
        target = log_id if log_id is not None else _latest_log_id(all_records)
        if target is None:
            return []

        cancelled = _cancelled(all_records)
        renames = [
            r
            for r in all_records
            if r.log_id == target
            and r.kind == _KIND_RENAME
            and (r.log_id, r.old, r.new) not in cancelled
        ]
        if not renames:
            return []
        if _is_undone(all_records, target):
            return []

        applied: list[UndoRecord] = []
        failed = False
        for rec in reversed(renames):
            try:
                apply_rename(self._rename, Path(rec.new), Path(rec.old))
            except OSError:
                failed = True
                continue
            undo_rec = UndoRecord(
                log_id=target,
                old=rec.new,
                new=rec.old,
                ts=self._clock(),
                kind=_KIND_UNDO,
            )
            self._write_record(undo_rec)
            applied.append(undo_rec)

        if not failed:
            marker = UndoRecord(
                log_id=target, old="", new="", ts=self._clock(), kind=_KIND_UNDONE
            )
            self._write_record(marker)
        return applied

    def rename_records(self, log_id: str) -> list[UndoRecord]:
        """该 log_id 的正向改名记录（按追加顺序）"""
        return [
            r for r in self._records() if r.log_id == log_id and r.kind == _KIND_RENAME
        ]

    def _records(self) -> list[UndoRecord]:
        """按追加顺序读取全部记录（文件不存在返回空）"""
        if not self.path.exists():
            return []
        records: list[UndoRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            records.append(UndoRecord.model_validate_json(line))
        return records

    def _write_record(self, record: UndoRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(record.model_dump_json() + "\n")


def _latest_log_id(records: list[UndoRecord]) -> str | None:
    """最近一次尚未撤销且未被抵消的正向批次的 log_id"""
    undone = {r.log_id for r in records if r.kind == _KIND_UNDONE}
    cancelled = _cancelled(records)
    for rec in reversed(records):
        if rec.kind != _KIND_RENAME:
            continue
        if rec.log_id in undone:
            continue
        if (rec.log_id, rec.old, rec.new) in cancelled:
            continue
        return rec.log_id
    return None


def _is_undone(records: list[UndoRecord], log_id: str) -> bool:
    return any(r.log_id == log_id and r.kind == _KIND_UNDONE for r in records)


def _cancelled(records: list[UndoRecord]) -> set[tuple[str, str, str]]:
    """被抵消记录标记为失效的 (log_id, old, new) 集合"""
    return {(r.log_id, r.old, r.new) for r in records if r.kind == _KIND_CANCEL}
