from __future__ import annotations

from renamer.core.compile.mapping import CompiledMapping
from renamer.core.compile.template import CompiledRenderTemplate
from renamer.core.dsl.format import BoundTransform, apply_bound

from ..context import Context
from ..stage import parse_mismatched


class RenderStage:
    """读取 parsed 与 fields 渲染 stem，应用输出格式后写入 target"""

    name = "render"

    def __init__(
        self,
        compiled: CompiledRenderTemplate,
        mapping: CompiledMapping,
        output_steps: tuple[BoundTransform, ...] = (),
    ) -> None:
        self._compiled = compiled
        self._mapping = mapping
        self._output_steps = output_steps

    def process(self, ctx: Context) -> None:
        if parse_mismatched(ctx):
            return

        def resolve(name: str) -> str | None:
            return self._mapping.render_value(name, ctx.parsed, ctx.fields)

        stem = self._compiled.render(resolve)
        ctx.target = apply_bound(stem, self._output_steps)
