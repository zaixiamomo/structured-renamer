"""流水线 stage 协议"""

from __future__ import annotations

from typing import Protocol

from .context import Context


class Stage(Protocol):
    """单个流水线步骤，就地改造 Context"""

    name: str

    def process(self, ctx: Context) -> None:
        """执行本步骤，读写都落在 ctx 上"""
        ...


def parse_mismatched(ctx: Context) -> bool:
    """解析模板不匹配是否已记录（后续 stage 据此短路，跳过其余步骤）"""
    return any(issue.code == "template_mismatch" for issue in ctx.issues)
