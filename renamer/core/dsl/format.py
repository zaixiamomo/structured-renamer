"""渲染语义：将中立调用表达式绑定为字符串变换，再执行已绑定的链。

语法只由 syntax 提供；操作的参数、说明与绑定逻辑在同一份注册定义中。
捕获约束属于 capture，本层不把它们解释为输出格式或逆向转换。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from .syntax import Call, fmt_expr, parse_expr

__all__ = [
    "BoundTransform",
    "apply_bound",
    "apply_chain",
    "compile_chain",
    "compile_expr",
    "fmt_expr",
    "list_formats",
    "parse_expr",
    "validate_call",
    "validate_expr",
]

Transform = Callable[[str], str]
_DIGIT_RE = re.compile(r"[0-9]+")
_DATE_PARTS_RE = re.compile(r"^(\d{4})[-/._]?(\d{1,2})[-/._]?(\d{1,2})$")


@dataclass(frozen=True)
class BoundTransform:
    """参数已经验证和绑定的单步变换，执行时不再查询注册表或解析参数。"""

    name: str
    transform: Transform

    def __call__(self, value: str) -> str:
        return self.transform(value)


@dataclass(frozen=True)
class _TransformDefinition:
    name: str
    params: tuple[str, ...]
    description: str
    factory: Callable[[tuple[str, ...]], Transform]

    def bind(self, args: tuple[str, ...]) -> BoundTransform:
        if len(args) != len(self.params):
            raise ValueError(
                f"格式函数 {self.name!r} 需要 {len(self.params)} 个参数"
                f"（{self.name}({', '.join(self.params)})），得到 {len(args)} 个"
            )
        return BoundTransform(self.name, self.factory(args))


def _constant(transform: Transform) -> Callable[[tuple[str, ...]], Transform]:
    """无需参数的变换仍经注册定义做统一参数绑定。"""
    return lambda _args: transform


def _identity(value: str) -> str:
    return value


def _bind_zpad(args: tuple[str, ...]) -> Transform:
    width_text = args[0]
    if not _DIGIT_RE.fullmatch(width_text):
        raise ValueError(f"zpad 宽度必须是整数，得到 {width_text!r}")
    width = int(width_text)
    return lambda value: value.zfill(width) if value else value


def _read_date(value: str) -> date | None:
    """输出格式需要真实日期；捕获侧的 date 仍只检查输入形状。"""
    match = _DATE_PARTS_RE.fullmatch(value)
    if match is None:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def _bind_strftime(args: tuple[str, ...]) -> Transform:
    pattern = args[0]

    def transform(value: str) -> str:
        parsed = _read_date(value)
        if parsed is None:
            return value
        try:
            return parsed.strftime(pattern)
        except ValueError:
            return value

    return transform


def _bind_replace(args: tuple[str, ...]) -> Transform:
    old, new = args
    return lambda value: value.replace(old, new) if old else value


_TRANSFORMS = {
    definition.name: definition
    for definition in (
        _TransformDefinition("string", (), "保留原文本", _constant(_identity)),
        _TransformDefinition("upper", (), "全部大写", _constant(str.upper)),
        _TransformDefinition("lower", (), "全部小写", _constant(str.lower)),
        _TransformDefinition("capitalize", (), "首字母大写", _constant(str.capitalize)),
        _TransformDefinition("trim", (), "去首尾空白", _constant(str.strip)),
        _TransformDefinition(
            "zpad", ("width",), "数字左补零到 width 位（不足才补）", _bind_zpad
        ),
        _TransformDefinition(
            "strftime",
            ("pattern",),
            "按 YMD 读词为日期后按 pattern 输出（失败透传）",
            _bind_strftime,
        ),
        _TransformDefinition(
            "replace",
            ("old", "new"),
            "把 old 替换为 new（old 为空透传）",
            _bind_replace,
        ),
    )
}


def list_formats() -> list[dict]:
    """可用格式与参数说明，与绑定器共用注册定义。"""
    return [
        {"id": item.name, "params": item.params, "description": item.description}
        for item in _TRANSFORMS.values()
    ]


def _bind_call(call: Call) -> BoundTransform:
    definition = _TRANSFORMS.get(call.name)
    if definition is None:
        raise ValueError(f"未知格式函数 {call.name!r}")
    return definition.bind(call.args)


def compile_chain(calls: tuple[Call, ...]) -> tuple[BoundTransform, ...]:
    """在编译期验证整条链并绑定参数；非法调用抛 ValueError。"""
    return tuple(_bind_call(call) for call in calls)


def compile_expr(spec: str) -> tuple[BoundTransform, ...]:
    return compile_chain(parse_expr(spec))


def validate_call(call: Call) -> str | None:
    """用真正的绑定器校验单步，避免校验与执行持有两套参数规则。"""
    try:
        _bind_call(call)
    except ValueError as exc:
        return str(exc)
    return None


def validate_expr(spec: str) -> list[str]:
    try:
        calls = parse_expr(spec)
    except ValueError as exc:
        return [str(exc)]
    return [message for call in calls if (message := validate_call(call))]


def apply_bound(value: str, steps: tuple[BoundTransform, ...]) -> str:
    """异常时保留失败步骤之前的值并终止链；正常透传仍继续后续步骤。"""
    for step in steps:
        try:
            value = step(value)
        except Exception:  # noqa: BLE001 输出变换失败保持已有文本
            return value
    return value


def apply_chain(value: str, calls: tuple[Call, ...]) -> str:
    """直接求值调用链；非法步骤保留之前已经完成的变换。"""
    for call in calls:
        try:
            step = _bind_call(call)
            value = step(value)
        except Exception:  # noqa: BLE001 与已绑定链使用同一运行时容错契约
            return value
    return value
