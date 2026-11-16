"""结果模型：FileResult、ReportSummary、Report"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from .issue import Issue


class Status(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CONFLICT = "conflict"


class FileResult(BaseModel):
    """单文件结果：源、目标、状态与诊断"""

    source: Path
    target: Path | None = None
    status: Status
    issues: list[Issue] = Field(default_factory=list)


class ReportSummary(BaseModel):
    total: int = 0
    success: int = 0
    failed: int = 0
    conflict: int = 0
    skipped: int = 0


class Report(BaseModel):
    log_id: str
    summary: ReportSummary
    items: list[FileResult] = Field(default_factory=list)
