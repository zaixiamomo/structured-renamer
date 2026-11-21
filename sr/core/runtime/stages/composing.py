"""把 render 片段组合为最终名称主体。"""

from dataclasses import replace

from sr.core.errors import PipelineError
from sr.core.runtime.context import PipelineContext
from sr.core.runtime.pipeline import PipelineStage
from sr.core.values import LiteralText, TokenValue


class ComposingStage(PipelineStage):
    """把 render 片段和字段值组合成结果。"""

    def process(self, context: PipelineContext) -> None:
        """渲染每个待处理文件的结果。"""
        for path in context.pending:
            file = context.files[path]
            if file.render is None or file.values is None:
                raise PipelineError("尚未准备正文字段，请先执行 ExtendingStage")
            with context.file_scope("composing", path):
                parts: list[str] = []
                for part in file.render.template.parts:
                    if isinstance(part, LiteralText):
                        parts.append(part.text)
                        continue
                    source = file.values[part.name]
                    cleaners = part.transform.cleaners if part.transform else ()
                    value = TokenValue(
                        value=part.apply(source.value, convert=False),
                        raw=source.raw,
                        operations=(*source.operations, *cleaners),
                    )
                    parts.append(value.value)
                result = file.render.transform.clean("".join(parts))
                context.files[path] = replace(file, result=result)
