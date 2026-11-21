"""按 render 模板取得最终字段。"""

from dataclasses import replace

from sr.core.compile.token import CompiledToken
from sr.core.errors import PipelineError
from sr.core.runtime.context import PipelineContext
from sr.core.runtime.pipeline import PipelineStage


class ExtendingStage(PipelineStage):
    """从 Evaluator 取齐 render 模板所需的字段。"""

    def process(self, context: PipelineContext) -> None:
        """按需执行拓展并写入文件字段。"""
        evaluator = context.require_evaluator()
        for path in context.pending:
            file = context.files[path]
            branch = file.render
            if branch is None:
                raise PipelineError("尚未完成正文选择，请先执行 SelectingStage")
            if path not in evaluator.sources:
                raise PipelineError("文件尚未完成来源绑定")
            names = dict.fromkeys(
                part.name
                for part in branch.template.parts
                if isinstance(part, CompiledToken)
            )
            with context.file_scope("extending", path):
                values = {name: evaluator.require(path, name) for name in names}
                context.files[path] = replace(file, values=values)
