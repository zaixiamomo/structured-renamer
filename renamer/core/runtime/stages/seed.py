from __future__ import annotations

from renamer.core.compile.mapping import CompiledMapping
from renamer.core.model import SOURCE_PATH_KEY

from ..context import Context
from ..stage import parse_mismatched


class SeedStage:
    """由 parsed 重建初始 fields，补入源路径；置于字段补全阶段之前"""

    name = "seed"

    def __init__(self, mapping: CompiledMapping) -> None:
        self._mapping = mapping

    def process(self, ctx: Context) -> None:
        if parse_mismatched(ctx):
            return
        ctx.fields = self._mapping.seed_values(ctx.parsed)
        ctx.fields.setdefault(SOURCE_PATH_KEY, str(ctx.source))
