"""按条件选择唯一的 render 分支。"""

from collections.abc import Iterator, Mapping
from dataclasses import replace
from pathlib import Path

from sr.core.compile.template_branch import CompiledTemplateBranch
from sr.core.compile.token import CompiledToken
from sr.core.errors import PipelineError
from sr.core.runtime.context import PipelineContext
from sr.core.runtime.evaluator import Evaluator
from sr.core.runtime.pipeline import PipelineStage
from sr.core.runtime.state import FileState


class _ConditionFields(Mapping[str, str]):
    """把 Evaluator 包装成按需读取的条件字段映射。"""

    def __init__(self, evaluator: Evaluator, path: Path) -> None:
        """保存求值器与成员路径。"""
        self.evaluator = evaluator
        self.path = path

    def __getitem__(self, name: str) -> str:
        """按需求值一个字段，未用到的字段不会触发失败。"""
        return self.evaluator.require(self.path, name).value

    def __iter__(self) -> Iterator[str]:
        """遍历捕获和生产者声明的字段名，不触发求值。"""
        source = self.evaluator.sources[self.path]
        names = dict.fromkeys(source.captures)
        names.update(dict.fromkeys(self.evaluator.producers[self.path]))
        return iter(names)

    def __len__(self) -> int:
        """返回可用字段名数量。"""
        return sum(1 for _ in self)

    def __contains__(self, name: object) -> bool:
        """判断字段存在且依赖链可生产。"""
        if not isinstance(name, str):
            return False
        if not self.evaluator.has_source(self.path, name):
            return False
        # 存在来源后强制求值，存在性同时反映依赖是否可生产。
        self[name]
        return True


class SelectingStage(PipelineStage):
    """按字段可生产性和条件选择 render 分支。"""

    def process(self, context: PipelineContext) -> None:
        """为每个文件选定唯一可用的 render 分支。"""
        evaluator = context.require_evaluator()
        for path in context.pending:
            file = context.files[path]
            if file.rule is None or not file.group or path not in evaluator.sources:
                raise PipelineError("尚未完成匹配、分组或来源绑定")
            with context.file_scope("selecting", path):
                candidates = tuple(
                    branch
                    for branch in file.rule.render
                    if all(
                        evaluator.can_produce(path, part.name)
                        for part in branch.template.parts
                        if isinstance(part, CompiledToken)
                    )
                )
                branch = self._select(
                    candidates,
                    _ConditionFields(evaluator, path),
                    file=file,
                )
                context.files[path] = replace(file, render=branch)

    def _select(
        self,
        branches: tuple[CompiledTemplateBranch, ...],
        fields: Mapping[str, str],
        *,
        file: FileState | None = None,
    ) -> CompiledTemplateBranch:
        """优先唯一条件分支，否则使用唯一无条件分支。"""
        selected: CompiledTemplateBranch | None = None
        fallbacks: list[CompiledTemplateBranch] = []
        for branch in branches:
            if branch.condition is None:
                fallbacks.append(branch)
            elif branch.condition.evaluate(fields, file=file):
                # 条件分支最多一个为真；多个为真视为歧义。
                if selected is not None:
                    raise ValueError("渲染分支歧义：多个条件分支为真")
                selected = branch
        if selected is not None:
            return selected
        # 没有任何条件命中时才回退到无条件分支。
        if len(fallbacks) > 1:
            raise ValueError("渲染分支歧义：多个无条件分支")
        if not fallbacks:
            raise ValueError("没有可用的渲染分支")
        return fallbacks[0]
