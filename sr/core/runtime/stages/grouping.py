"""按规则的分组声明建立组关系。"""

from dataclasses import replace
from pathlib import Path

from sr.core.compile.group import CompiledGroup
from sr.core.errors import PipelineError
from sr.core.runtime.context import PipelineContext
from sr.core.runtime.pipeline import PipelineStage
from sr.core.values import TokenValue


class GroupingStage(PipelineStage):
    """按分组声明把同目录文件划成组。"""

    def process(self, context: PipelineContext) -> None:
        """为每个文件确定同组成员。"""
        buckets: dict[
            tuple[int, str, int],
            tuple[CompiledGroup, dict[Path, TokenValue]],
        ] = {}

        for path in context.pending:
            file = context.files[path]
            rule = file.rule
            if rule is None:
                raise PipelineError("尚未完成匹配，请先执行 MatchingStage")
            # 默认每个文件自成一组，分组声明成功后才替换。
            context.files[path] = replace(file, group=(path,))
            if not rule.group:
                continue

            for index, group in enumerate(rule.group):
                token = file.captures.get(group.token.name)
                if token is None or token.value == "":
                    continue

                parent = str(file.path.parent)
                # CompiledRule 不可哈希，用 id 区分；同目录、同序号的声明共享一个桶。
                key = (id(rule), parent, index)
                if key not in buckets:
                    buckets[key] = (group, {})
                buckets[key][1][path] = token
                # 每条规则只使用第一个命中的分组声明。
                break

        for group, values in buckets.values():
            with context.file_scope("grouping", *values):
                groups = group.split(values)
                for members in groups:
                    for path in members:
                        context.files[path] = replace(
                            context.files[path], group=members
                        )
