"""anime 领域：Bangumi 信息搜索能力（bangumi_search）"""

from __future__ import annotations

from renamer.core.model import Field, FieldKey, FieldType
from renamer.core.plugins.domain import Domain
from renamer.core.ports import HttpClient

from .web_bangumi_search import CAPABILITY as BANGUMI_SEARCH
from .web_bangumi_search import make_bangumi_search

__all__ = ["build_calls", "domain"]

_F = FieldKey.parse

FIELDS: tuple[Field, ...] = (
    Field(key=_F("anime:TITLE"), type=FieldType.STRING),
    Field(key=_F("anime:DATE"), type=FieldType.STRING),
    Field(key=_F("anime:NAME_CN"), type=FieldType.STRING),
)

CAPABILITIES: tuple = (BANGUMI_SEARCH,)


def build_calls(getter: HttpClient | None = None):
    """WEB 能力注入 getter，未注入时能力函数恒返回 None"""
    return {
        BANGUMI_SEARCH.id: make_bangumi_search(getter),
    }


domain = Domain(
    name="anime",
    fields=FIELDS,
    capabilities=CAPABILITIES,
    build_calls=build_calls,
)
