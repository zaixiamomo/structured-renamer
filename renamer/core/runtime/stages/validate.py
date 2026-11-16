"""validate stage：required 字段填充 / 空目标 / 超长校验，只记 issue 不做 I/O"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from renamer.core.model import FieldKey, Issue, Level

from ..context import Context
from ..stage import parse_mismatched

WINDOWS_MAX_NAME = 255
WINDOWS_MAX_PATH = 260


class ValidateStage:
    """校验目标名，required 字段按存在性判定（空串合法），缺失/空/超长逐项记 issue"""

    name = "validate"

    def __init__(self, required: Sequence[FieldKey]) -> None:
        self._required = list(required)

    def process(self, ctx: Context) -> None:
        if parse_mismatched(ctx):
            return
        if not ctx.target:
            ctx.issues.append(
                Issue(level=Level.ERROR, code="empty_target", message="目标名为空")
            )
            return
        missing = [key for key in self._required if key not in ctx.fields]
        if missing:
            ctx.issues.append(
                Issue(
                    level=Level.ERROR,
                    code="missing_field",
                    message=f"缺字段 {missing[0]}",
                )
            )
        if _too_long(ctx.target, ctx.source):
            ctx.issues.append(
                Issue(level=Level.ERROR, code="target_too_long", message="目标路径超长")
            )


def _too_long(target: str, source: Path) -> bool:
    """文件名或拼接后路径超长检查，原地改名故父目录取源路径"""
    if len(target) > WINDOWS_MAX_NAME:
        return True
    return len(str(source.parent / target)) > WINDOWS_MAX_PATH
