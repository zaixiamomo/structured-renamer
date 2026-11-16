"""parse stage：剥离扩展名并反向解析 stem，捕获值写入 parsed 槽"""

from __future__ import annotations

from renamer.core.compile.template import CompiledParseTemplate
from renamer.core.model import Issue, Level

from ..context import Context


class ParseStage:
    """剥扩展名并解析 stem，不匹配记 template_mismatch 供后续 stage 短路"""

    name = "parse"

    def __init__(self, compiled: CompiledParseTemplate) -> None:
        self._compiled = compiled

    def process(self, ctx: Context) -> None:
        # 扩展名先剥离，解析与渲染只对 stem 操作，最后拼回，机制上禁止改扩展名
        ctx.suffix = ctx.source.suffix
        parsed = self._compiled.parse(ctx.source.stem)
        if parsed is None:
            ctx.issues.append(
                Issue(
                    level=Level.ERROR,
                    code="template_mismatch",
                    message="解析模板不匹配",
                )
            )
            return
        ctx.parsed = parsed
