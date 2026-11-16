"""撤销记录"""

from __future__ import annotations

from pydantic import BaseModel


class UndoRecord(BaseModel):
    log_id: str
    old: str
    new: str
    ts: float
    kind: str
