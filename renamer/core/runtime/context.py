"""运行时状态：Context"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from renamer.core.model import FieldKey, Issue


class Context(BaseModel):
    """单文件阶段共享状态；parsed 为捕获值，fields 为种子及能力结果"""

    source: Path
    suffix: str = ""
    parsed: dict[str, str]
    fields: dict[FieldKey, str]
    # Render 写入 stem，Sanitize 清理并拼接 suffix 后成为完整目标名
    target: str | None = None
    issues: list[Issue]
