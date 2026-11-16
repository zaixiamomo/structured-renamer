"""mapping 文法：``a=b=c`` 与 TokenMapping 的互逆转换（唯一来源，含 FieldKey 判别）

``parse_mapping`` 与 ``fmt_mapping`` 互逆；codec 只引用这里，不再各自重判 ``=``
分段与 ``:`` 前缀。TokenMapping 本身是纯数据，不携带序列化文法——本层直接构造
或格式化它，故 mapping 文法对 model 的依赖方向与分层一致（dsl → model）。
"""

from __future__ import annotations

from renamer.core.model.field import FieldKey
from renamer.core.model.rule import TokenMapping

__all__ = ["fmt_mapping", "parse_mapping"]


def parse_mapping(text: str) -> TokenMapping:
    """把字符串形态的 mapping 解析为 TokenMapping

    支持形态：恒等 ``title``、异名 ``biaoti=title``、显式同名 ``title=anime:TITLE``、
    别名 ``biaoti=title=anime:TITLE``、render-only ``date=anime:DATE``。

    Raises:
        ValueError: 格式非法
    """
    raw = text.strip()
    if not raw:
        raise ValueError("mapping 不能为空")
    parts = [p.strip() for p in raw.split("=")]
    if len(parts) == 1:
        return TokenMapping(parse_token=parts[0])
    if len(parts) == 2:
        # 两段式：RHS 可解析为 FieldKey 时是 field_key，否则是 render_token
        try:
            FieldKey.parse(parts[1])
        except ValueError:
            return TokenMapping(parse_token=parts[0], render_token=parts[1])
        return TokenMapping(parse_token=parts[0], field_key=parts[1])
    if len(parts) == 3:
        return TokenMapping(
            parse_token=parts[0], render_token=parts[1], field_key=parts[2]
        )
    raise ValueError(
        f"非法 mapping {text!r}：应为恒等名或 'parse=render' 或 'parse=render=domain:FIELD'"
    )


def fmt_mapping(mapping: TokenMapping) -> str:
    """把 TokenMapping 规范化为 mapping 字符串（与 parse_mapping 互逆）"""
    parse_token, render_token, field_key = (
        mapping.parse_token,
        mapping.render_token,
        mapping.field_key,
    )
    if field_key is None:
        if render_token == parse_token:
            return parse_token
        return f"{parse_token}={render_token}"
    if render_token == parse_token:
        return f"{parse_token}={field_key}"
    return f"{parse_token}={render_token}={field_key}"
