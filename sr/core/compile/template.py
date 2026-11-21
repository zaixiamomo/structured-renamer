"""模板文本的解析与匹配。"""

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from sr.core.compile.token import CompiledToken, Token
from sr.core.contracts.compilable import Compilable
from sr.core.values import LiteralText, TokenValue

DEFAULT_TEMPLATE_DELIMITER_OPEN = "{"
DEFAULT_TEMPLATE_DELIMITER_CLOSE = "}"
TemplateUsage = Literal["parse", "render"]


@dataclass(frozen=True)
class CompiledTemplate:
    """模板编译后的片段序列与匹配模式。"""

    parts: tuple[CompiledToken | LiteralText, ...]
    pattern: re.Pattern[str] | None

    def match(self, text: str) -> dict[str, TokenValue] | None:
        """用完整匹配提取字段。

        Args:
            text: 已应用模板级加工的文本。
        Returns:
            字段名到 TokenValue 的映射；不匹配时返回 None。
        """
        if self.pattern is None:
            return None
        match = self.pattern.fullmatch(text)
        if match is None:
            return None
        captures: dict[str, TokenValue] = {}
        for index, part in enumerate(self.parts):
            if not isinstance(part, CompiledToken) or part.name == "_":
                # 忽略词段没有捕获组，也不进入字段。
                continue
            # 捕获组按片段序号命名，避免字段名进入正则语法。
            raw = match.group(f"t{index}")
            captures[part.name] = TokenValue(
                value=part.apply(raw, convert=False),
                raw=raw,
                operations=part.transform.cleaners,
            )
        return captures


class Template(BaseModel, Compilable[CompiledTemplate]):
    """带定界符的模板声明。"""

    text: str
    open: str = DEFAULT_TEMPLATE_DELIMITER_OPEN
    close: str = DEFAULT_TEMPLATE_DELIMITER_CLOSE

    model_config = ConfigDict(frozen=True, extra="forbid")

    def compile(self, usage: TemplateUsage) -> CompiledTemplate:
        """按用途编译模板。

        Args:
            usage: parse 生成匹配模式，render 只保留片段序列。
        Returns:
            CompiledTemplate。
        Raises:
            ValueError: 定界符或词段不合法。
            SyntaxError: 加工表达式语法错误。
        """
        if usage == "parse":
            return self._compile_parse()
        return self._compile_render()

    def _compile_parse(self) -> CompiledTemplate:
        """编译 parse 模板并校验忽略词段。"""
        parts = self._compile_parts()
        self._check_duplicates(parts)
        if any(
            isinstance(part, CompiledToken)
            and part.name == "_"
            and part.transform.cleaners
            for part in parts
        ):
            raise ValueError("忽略词段不支持加工链")
        pattern = self._compile_pattern(parts)
        return CompiledTemplate(parts=parts, pattern=pattern)

    def _compile_render(self) -> CompiledTemplate:
        """编译 render 模板，拒绝忽略词段。"""
        parts = self._compile_parts()
        if any(isinstance(part, CompiledToken) and part.name == "_" for part in parts):
            raise ValueError("忽略词段只能用于 parse 模板")
        return CompiledTemplate(parts=parts, pattern=None)

    def _compile_parts(self) -> tuple[CompiledToken | LiteralText, ...]:
        """扫描定界符并编译词段片段。"""
        if not self.open or not self.close:
            raise ValueError("模板定界符不能为空")
        parts: list[CompiledToken | LiteralText] = []
        position = 0

        while position < len(self.text):
            start = self.text.find(self.open, position)
            if start == -1:
                parts.append(LiteralText(self.text[position:]))
                break
            if start > position:
                parts.append(LiteralText(self.text[position:start]))

            content_start = start + len(self.open)
            end = self.text.find(self.close, content_start)
            if end == -1:
                raise ValueError("模板词段缺少闭合定界符")
            # 定界符之间的内容交给词段解析。
            parts.append(Token(self.text[content_start:end]).compile("transform"))
            position = end + len(self.close)

        return tuple(parts)

    def _check_duplicates(self, parts: tuple[CompiledToken | LiteralText, ...]) -> None:
        """拒绝重复的具名字段。"""
        names: set[str] = set()
        for part in parts:
            # _ 是忽略词段，可以重复出现。
            if isinstance(part, CompiledToken) and part.name != "_":
                if part.name in names:
                    raise ValueError(f"重复字段名称：{part.name}")
                names.add(part.name)

    def _compile_pattern(
        self, parts: tuple[CompiledToken | LiteralText, ...]
    ) -> re.Pattern[str]:
        """把片段拼成完整匹配的正则。"""
        fragments: list[str] = []
        for index, part in enumerate(parts):
            if isinstance(part, LiteralText):
                fragments.append(re.escape(part.text))
                continue

            # 有类别的词段限制在类别范围内，否则匹配任意字符。
            ranges = part.classify.ranges if part.classify is not None else ""
            if ranges:
                capture = f"[{ranges}]+?"
            else:
                capture = r"[\s\S]+?"
            # 非贪婪配合 fullmatch，让前面的字段尽量短；忽略词段用非捕获组。
            fragments.append(
                f"(?:{capture})" if part.name == "_" else f"(?P<t{index}>{capture})"
            )

        return re.compile("".join(fragments))
