"""模板草稿：有序字面量/词段为权威，示例字符与匹配范围为可选投影。

新建时可在示例上划词；加载时直接恢复模板片段，不依赖示例文件。原文拼写
只作为未编辑片段的保真基线，改名和注解始终读取当前 tokens。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from renamer.core.dsl.capture import capture_discriminable
from renamer.core.dsl.syntax import Call, escape_literal, fmt_draft_placeholder
from renamer.core.model.template import ParseTemplate

from .segment import Span, segment

__all__ = ["SourceTemplate"]


def _capture_annotation(type: str, values: tuple[str, ...]) -> tuple[Call, ...] | None:
    """旧 GUI 类型/候选值参数转 AST；仅存在于作者接口边界。"""
    if type == "string":
        return None
    return (Call(type, tuple(values) if type == "enum" else ()),)


@dataclass(frozen=True)
class _Literal:
    text: str
    raw: str


@dataclass
class SourceTemplate:
    """可编辑模板片段；示例字符及捕获范围是可选的显示投影。"""

    chars: list[str] = field(default_factory=list)
    tokens: dict[int, Span] = field(default_factory=dict)  # id -> token 词段
    open: str = "{"
    close: str = "}"
    _parts: list[_Literal | int] = field(default_factory=list, init=False, repr=False)
    _spellings: dict[int, Span] = field(default_factory=dict, init=False, repr=False)
    _sample_available: bool = field(default=True, init=False, repr=False)
    _loaded: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self.chars = list(self.chars)
        cursor = 0
        for tid, token in sorted(self.tokens.items(), key=lambda item: item[1].s):
            self._append_literal("".join(self.chars[cursor : token.s]))
            self._parts.append(tid)
            cursor = token.e + 1
        self._append_literal("".join(self.chars[cursor:]))

    @classmethod
    def from_template(cls, template: ParseTemplate) -> SourceTemplate:
        """加载模板原文，不伪造示例值；未编辑的片段保持原始拼写。"""
        document = cls(open=template.open, close=template.close)
        document._sample_available = False
        document._loaded = True
        for part in segment(template.text, template.open, template.close).spans:
            if not part.is_token():
                document._parts.append(_Literal(part.text, part.raw))
                continue
            tid = document.new_token_id()
            document.tokens[tid] = replace(part, text="")
            document._spellings[tid] = part
            document._parts.append(tid)
        return document

    @property
    def has_sample(self) -> bool:
        return self._sample_available

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def ordered_tokens(self) -> list[tuple[int, Span]]:
        return [
            (part, self.tokens[part]) for part in self._parts if isinstance(part, int)
        ]

    def sample_text(self, tid: int) -> str | None:
        return self.tokens[tid].text if self.has_sample else None

    def attach_sample(self, text: str, spans: tuple[tuple[str, int, int], ...]) -> None:
        """应用编译层提供的匹配范围；不改变模板文本、注解或词段身份。"""
        by_name = {name: (start, end) for name, start, end in spans}
        projected: dict[int, Span] = {}
        cursor = 0
        for part in self._parts:
            if isinstance(part, _Literal):
                if not text.startswith(part.text, cursor):
                    raise ValueError("示例文件名与模板不匹配")
                cursor += len(part.text)
                continue
            token = self.tokens[part]
            if token.name not in by_name:
                raise ValueError("示例缺少模板捕获")
            start, end = by_name[token.name]
            if start != cursor or end < start - 1 or end >= len(text):
                raise ValueError("示例捕获范围不一致")
            projected[part] = replace(token, s=start, e=end, text=text[start : end + 1])
            cursor = end + 1
        if cursor != len(text):
            raise ValueError("示例文件名与模板不匹配")
        self.chars = list(text)
        self.tokens.update(projected)
        self._sample_available = True

    def clear_sample(self) -> None:
        self.chars = []
        self.tokens = {
            tid: replace(token, s=-1, e=-1, text="")
            for tid, token in self.tokens.items()
        }
        self._sample_available = False

    def _append_literal(self, text: str) -> None:
        if text:
            self._parts.append(
                _Literal(text, escape_literal(text, self.open, self.close))
            )

    # 词段 id：优先复用已删除释放的最小编号
    def new_token_id(self) -> int:
        used = set(self.tokens)
        i = 1
        while i in used:
            i += 1
        return i

    def token_of(self) -> list[int | None]:
        """每字符归属的 token id（只读派生，None 为字面量）"""
        out: list[int | None] = [None] * len(self.chars)
        for tid, sp in self.tokens.items():
            for i in range(max(0, sp.s), min(sp.e, len(self.chars) - 1) + 1):
                out[i] = tid
        return out

    def occupied(self, s: int, e: int) -> bool:
        """[s, e] 是否与已有词段重叠"""
        token_of = self.token_of()
        return any(token_of[i] is not None for i in range(s, e + 1))

    def mark(
        self,
        s: int,
        e: int,
        name: str | None = None,
        type: str = "string",
        values: tuple[str, ...] = (),
        *,
        annotation: tuple[Call, ...] | None = None,
    ) -> int:
        """划词：把 [s, e] 标为 token 词段，返回新 id；name 缺省为 ``token{id}``

        Raises:
            ValueError: 区间越界或与已有词段重叠
        """
        if not self.has_sample or s < 0 or e >= len(self.chars) or s > e:
            raise ValueError(f"词段区间 [{s},{e}] 越界")
        if self.occupied(s, e):
            raise ValueError(f"词段区间 [{s},{e}] 与已有词段重叠")
        cursor = 0
        for index, part in enumerate(self._parts):
            length = (
                len(part.text)
                if isinstance(part, _Literal)
                else len(self.tokens[part].text)
            )
            if isinstance(part, _Literal) and cursor <= s <= e < cursor + length:
                before, after = part.text[: s - cursor], part.text[e - cursor + 1 :]
                break
            cursor += length
        else:
            raise ValueError("划词区间跨越已有捕获（包括空捕获）")
        text = "".join(self.chars[s : e + 1])
        tid = self.new_token_id()
        self.tokens[tid] = Span(
            "tok",
            s,
            e,
            text,
            name=name or f"token{tid}",
            annotation=(
                tuple(annotation)
                if annotation is not None
                else _capture_annotation(type, values)
            ),
            raw=text,
        )
        replacement: list[_Literal | int] = []
        if before:
            replacement.append(
                _Literal(before, escape_literal(before, self.open, self.close))
            )
        replacement.append(tid)
        if after:
            replacement.append(
                _Literal(after, escape_literal(after, self.open, self.close))
            )
        self._parts[index : index + 1] = replacement
        return tid

    def unmark(self, tid: int) -> None:
        token = self.tokens.pop(tid, None)
        if token is None:
            return
        self._spellings.pop(tid, None)
        value = token.text if self.has_sample else ""
        index = self._parts.index(tid)
        self._parts[index : index + 1] = (
            [_Literal(value, escape_literal(value, self.open, self.close))]
            if value
            else []
        )
        merged: list[_Literal | int] = []
        for part in self._parts:
            if (
                isinstance(part, _Literal)
                and merged
                and isinstance(merged[-1], _Literal)
            ):
                previous = merged[-1]
                merged[-1] = _Literal(
                    previous.text + part.text, previous.raw + part.raw
                )
            else:
                merged.append(part)
        self._parts = merged

    def rename(self, tid: int, name: str) -> None:
        sp = self.tokens.get(tid)
        if sp is not None:
            self.tokens[tid] = replace(sp, name=name)

    def set_type(self, tid: int, type: str) -> None:
        """保留旧 GUI 写口，更新同一份注解 AST。"""
        sp = self.tokens.get(tid)
        if sp is not None:
            self.set_annotation(tid, _capture_annotation(type, sp.values or ()))

    def set_values(self, tid: int, values: tuple[str, ...]) -> None:
        """保留旧 GUI 的候选值编辑入口，不持有平行 values 状态。"""
        sp = self.tokens.get(tid)
        if sp is not None:
            name = sp.annotation[0].name if sp.annotation else "string"
            self.set_annotation(tid, _capture_annotation(name, values))

    def set_annotation(self, tid: int, annotation: tuple[Call, ...] | None) -> None:
        """替换词段的注解；允许编辑中的未校验 AST。"""
        sp = self.tokens.get(tid)
        if sp is not None:
            value = tuple(annotation) if annotation is not None else None
            self.tokens[tid] = replace(sp, annotation=value)

    def render_text(self) -> str:
        """未编辑片段保留原文，编辑后的占位符统一从注解 AST 序列化。"""
        parts: list[str] = []
        for part in self._parts:
            if isinstance(part, _Literal):
                parts.append(part.raw)
                continue
            token = self.tokens[part]
            original = self._spellings.get(part)
            if original and (original.name, original.annotation) == (
                token.name,
                token.annotation,
            ):
                parts.append(original.raw)
            else:
                parts.append(
                    fmt_draft_placeholder(
                        token.name or "", token.annotation, self.open, self.close
                    )
                )
        return "".join(parts)

    def to_template(self) -> ParseTemplate:
        """词流组装为解析模板"""
        return ParseTemplate(text=self.render_text(), open=self.open, close=self.close)

    def adjacent_conflicts(self) -> set[int]:
        """相邻 token（中间无字面量）且两侧都非可判别类型，返回冲突 token id 集合"""
        return {tid for pair in self.adjacent_conflict_pairs() for tid in pair}

    def adjacent_conflict_pairs(self) -> list[tuple[int, int]]:
        """按词流顺序返回无法判别边界的相邻 token id 对。"""
        pairs: list[tuple[int, int]] = []
        previous: int | None = None
        for part in self._parts:
            if isinstance(part, _Literal):
                if part.text:
                    previous = None
                continue
            annotation = self.tokens[part].annotation
            name = (
                annotation[0].name if annotation and len(annotation) == 1 else "string"
            )
            if capture_discriminable(name):
                previous = None
                continue
            if previous is not None:
                pairs.append((previous, part))
            previous = part
        return pairs
