"""规则 Rule：解析与渲染模板、恒等映射、能力调用"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .field import FieldKey


class TokenMapping(BaseModel):
    """mapping 简写声明，render_token 缺省取左侧同名

    parse_token 保存简写左侧名称，可能是解析捕获名或仅用于字段渲染的名称
    实际解析来源由编译时的模板上下文决定，字符串文法在 core/dsl/mapping
    """

    parse_token: str
    render_token: str | None = None
    field_key: FieldKey | None = None

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def _check_tokens(self) -> TokenMapping:
        if not self.parse_token:
            raise ValueError("parse_token 不能为空")
        if self.render_token is None:
            object.__setattr__(self, "render_token", self.parse_token)
        elif not self.render_token:
            raise ValueError("render_token 不能为空")
        return self


class CapabilityCall(BaseModel):
    """Rule 内显式 func 调用：表面只写 func 与 out"""

    func: str
    out: tuple[str, ...] = ()

    model_config = ConfigDict(frozen=True)


class Rule(BaseModel):
    """一次改名任务的完整规则"""

    name: str
    parse_template: str
    render_template: str
    mappings: tuple[TokenMapping, ...] = ()
    capabilities: tuple[CapabilityCall, ...] = ()
    format: str = Field(
        default="", description="输出级格式链：作用于拼好的整串 stem（sanitize 之前）"
    )

    model_config = ConfigDict(frozen=True)
