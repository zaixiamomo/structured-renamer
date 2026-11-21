"""按规则和 parse 分支匹配文件名主体。"""

import math
from collections.abc import Mapping
from dataclasses import replace

from sr.core.compile.rule import CompiledRule
from sr.core.compile.template_branch import CompiledTemplateBranch
from sr.core.compile.token import CompiledToken
from sr.core.runtime.context import PipelineContext
from sr.core.runtime.pipeline import PipelineStage
from sr.core.runtime.state import FileState
from sr.core.values import LiteralText, TokenValue

# Unicode 最大码点数，用于把字符类别大小换算成信息量。
_ALPHABET = 0x110000
_LOG_ALPHABET = math.log2(_ALPHABET)


class MatchingStage(PipelineStage):
    """为每个文件选定唯一的规则和 parse 分支。"""

    def process(self, context: PipelineContext) -> None:
        """匹配每个待处理文件的名称主体。"""
        for path in context.pending:
            with context.file_scope("matching", path):
                matched = self._match_file(
                    path.stem, context.rules, context.files[path]
                )
                context.files[path] = matched

    def _match_file(
        self, text: str, rules: tuple[CompiledRule, ...], file: FileState
    ) -> FileState:
        """在全部规则中选出唯一匹配。"""
        matches: list[FileState] = []
        for rule in rules:
            matched = self._match_rule(text, rule, file)
            if matched is not None:
                matches.append(matched)
        if not matches:
            raise ValueError("未匹配任何规则")
        if len(matches) > 1:
            raise ValueError("匹配多个模板失败：同时匹配多个规则")
        return matches[0]

    def _match_rule(
        self, text: str, rule: CompiledRule, file: FileState
    ) -> FileState | None:
        """在规则内按具体度选出唯一分支。"""
        matches: list[tuple[FileState, float, int]] = []
        for index, branch in enumerate(rule.parse):
            tokens = branch.match(text, file=file)
            if tokens is None:
                continue
            matches.append(
                (
                    replace(file, rule=rule, parse=branch, captures=tokens),
                    self._specificity(branch, tokens),
                    index,
                )
            )
        if not matches:
            return None
        best = max(score for _, score, _ in matches)
        selected = [item for item in matches if item[1] == best]
        # 同等具体度视为歧义，而不是依赖声明顺序。
        if len(selected) > 1:
            indices = ", ".join(str(item[2] + 1) for item in selected)
            raise ValueError(f"匹配多个模板失败：规则内存在同等严格的分支：{indices}")
        return selected[0][0]

    def _specificity(
        self,
        branch: CompiledTemplateBranch,
        captures: Mapping[str, TokenValue],
    ) -> float:
        """估算分支对文本的约束强度。"""
        score = 0.0
        for part in branch.template.parts:
            if isinstance(part, LiteralText):
                # 字面量每字符提供 log2(字母表) 的约束。
                score += len(part.text) * _LOG_ALPHABET
                continue
            if not isinstance(part, CompiledToken):
                continue
            classify = part.classify
            if classify is None or not classify.classifiers:
                continue
            captured = captures.get(part.name)
            length = len(captured.raw) if captured is not None else 1
            size = min(classify.size, _ALPHABET)
            # 类别越小，命中字符携带的约束越强；捕获越长权重越高。
            if size > 0:
                score += length * math.log2(_ALPHABET / size)
        return score
