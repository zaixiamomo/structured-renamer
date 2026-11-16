"""统一错误值：全项目唯一诊断类型"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class Level(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class Issue(BaseModel):
    """错误原子：级别、错误码、可读消息"""

    level: Level
    code: str
    message: str

    model_config = ConfigDict(frozen=True)


class PlanError(Exception):
    """编译期异常，持有 Issue 列表供编排层统一汇报"""

    def __init__(self, issues: list[Issue]) -> None:
        self.issues = issues
        super().__init__("；".join(i.message for i in issues))
