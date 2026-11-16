"""领域库：模板与规则集合（模板按角色分两表，规则引用名按角色查对应表）"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .rule import Rule
from .template import ParseTemplate, RenderTemplate


class Library(BaseModel):
    parse_templates: dict[str, ParseTemplate] = Field(default_factory=dict)
    render_templates: dict[str, RenderTemplate] = Field(default_factory=dict)
    rules: dict[str, Rule] = Field(default_factory=dict)
