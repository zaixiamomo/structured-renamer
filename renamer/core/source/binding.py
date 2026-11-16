"""可变编辑态绑定，转为持久态简写后按模板上下文解释来源"""

from __future__ import annotations

from dataclasses import dataclass

from renamer.core.model.field import FieldKey
from renamer.core.model.rule import TokenMapping

__all__ = ["Binding"]


@dataclass
class Binding:
    """编辑态词段的规范绑定：三要素缺省即未绑定"""

    parse_token: str | None = None  # 解析模板中的 token 名，None = render-only
    render_token: str | None = None  # 渲染模板中的 token 名，None = 取 parse_token
    field_key: FieldKey | None = None  # 绑定的规范字段，None = 未绑定 / 纯透传

    def effective_render_token(self) -> str | None:
        """渲染引用名：render_token 缺省回落到 parse_token"""
        return self.render_token if self.render_token is not None else self.parse_token

    def is_identity(self) -> bool:
        """恒等映射：render_token 未显式指定或与 parse_token 同名"""
        return self.render_token is None or self.render_token == self.parse_token

    def to_mapping(self) -> TokenMapping:
        """直构 TokenMapping，parse_token 保存简写左侧名称"""
        if self.parse_token is not None:
            return TokenMapping(
                parse_token=self.parse_token,
                render_token=None if self.is_identity() else self.render_token,
                field_key=self.field_key,
            )
        return TokenMapping(
            parse_token=self.render_token or "",
            render_token=None,
            field_key=self.field_key,
        )
