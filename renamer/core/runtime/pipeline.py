"""流水线编排，按序执行固定 stage 序列"""

from __future__ import annotations

from collections.abc import Sequence

from .context import Context
from .stage import Stage


class Pipeline:
    """固定 stage 序列，run 按序执行并全程累积 issue，不注入任何值"""

    def __init__(self, stages: Sequence[Stage]) -> None:
        self._stages = list(stages)

    def run(self, ctx: Context) -> None:
        """按序执行各 stage，副作用与 issue 就地写入 ctx"""
        for stage in self._stages:
            stage.process(ctx)
