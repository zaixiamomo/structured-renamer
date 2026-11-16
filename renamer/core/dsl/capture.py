"""捕获操作定义、绑定及编辑辅助，不转换捕获原文"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .syntax import Call

__all__ = [
    "BoundCapture",
    "CaptureError",
    "adjacent_capture_conflicts",
    "bind_capture",
    "capture_discriminable",
    "infer_type",
]

# 捕获和示例推断只检查日期形状，不验证日历日期
_DATE_PATTERN = r"\d{4}[-/._]?\d{1,2}[-/._]?\d{1,2}"
_DATE_RE = re.compile(_DATE_PATTERN)


class CaptureError(ValueError):
    """捕获操作错误，供模板编译器转换为带稳定错误码的 Issue"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class BoundCapture:
    """无捕获组的正则片段及编辑、相邻判定所需的语义元数据"""

    pattern: str
    field_type: str
    discriminable: bool


@dataclass(frozen=True)
class _CaptureDefinition:
    name: str
    field_type: str
    discriminable: bool
    factory: Callable[[tuple[str, ...]], str]

    def bind(self, args: tuple[str, ...]) -> BoundCapture:
        return BoundCapture(self.factory(args), self.field_type, self.discriminable)


def _without_args(name: str, pattern: str) -> Callable[[tuple[str, ...]], str]:
    def bind(args: tuple[str, ...]) -> str:
        if args:
            raise CaptureError(
                "template_unexpected_values", f"捕获操作 {name!r} 不接受参数"
            )
        return pattern

    return bind


def _bind_enum(args: tuple[str, ...]) -> str:
    if not args or any(value == "" for value in args):
        raise CaptureError(
            "template_invalid_enum", "捕获操作 'enum' 需要至少一个非空候选值"
        )
    return "(?:" + "|".join(re.escape(value) for value in args) + ")"


_CAPTURES = {
    definition.name: definition
    for definition in (
        _CaptureDefinition("string", "string", False, _without_args("string", ".*?")),
        _CaptureDefinition("int", "int", True, _without_args("int", r"\d+")),
        _CaptureDefinition("date", "date", True, _without_args("date", _DATE_PATTERN)),
        _CaptureDefinition("enum", "enum", True, _bind_enum),
    )
}


def capture_discriminable(name: str) -> bool | None:
    """编辑中的参数可以尚未完整，只读取定义的边界判别属性"""
    definition = _CAPTURES.get(name)
    return definition.discriminable if definition is not None else None


def bind_capture(annotation: tuple[Call, ...] | None) -> BoundCapture:
    """缺省注解匹配任意文本，解析侧只接受一个捕获约束"""
    calls = annotation or (Call("string"),)
    if len(calls) != 1:
        raise CaptureError("template_capture_chain", "解析模板只允许一个捕获操作")
    call = calls[0]
    definition = _CAPTURES.get(call.name)
    if definition is None:
        raise CaptureError("template_unknown_type", f"未知捕获操作 {call.name!r}")
    return definition.bind(call.args)


def infer_type(text: str) -> str:
    """按示例推断捕获操作，纯数字优先于日期形状，其余为 string"""
    if text.isdigit():
        return "int"
    if _DATE_RE.fullmatch(text):
        return "date"
    return "string"


def adjacent_capture_conflicts(items: Sequence[tuple[bool, bool]]) -> set[int]:
    """按 (是否捕获, 是否可判别) 检查相邻项，返回冲突捕获的序数"""
    bad: set[int] = set()
    prev_discriminable = False
    prev_idx = -1
    token_idx = 0
    for is_token, discriminable in items:
        if is_token:
            if prev_idx >= 0 and not prev_discriminable and not discriminable:
                bad.add(prev_idx)
                bad.add(token_idx)
            prev_discriminable = discriminable
            prev_idx = token_idx
            token_idx += 1
        else:
            prev_discriminable = False
            prev_idx = -1
    return bad
