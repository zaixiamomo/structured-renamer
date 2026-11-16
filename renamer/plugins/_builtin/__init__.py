"""_builtin 领域：文件级兜底，从 mkv 原始路径读取分辨率（file_resolution 能力）"""

from __future__ import annotations

from renamer.core.model import SOURCE_PATH_KEY, Field, FieldKey, FieldType
from renamer.core.plugins.domain import Domain
from renamer.core.ports import HttpClient

from .info_file_resolution import CAPABILITY as FILE_RESOLUTION
from .info_file_resolution import make_resolution

__all__ = ["build_calls", "domain"]

_F = FieldKey.parse

FIELDS: tuple[Field, ...] = (
    Field(key=SOURCE_PATH_KEY, type=FieldType.STRING),
    Field(key=_F("_builtin:RESOLUTION"), type=FieldType.STRING),
)

CAPABILITIES: tuple = (FILE_RESOLUTION,)


def build_calls(getter: HttpClient | None = None):
    """INFO 能力不用网络，getter 保留以统一签名"""
    return {FILE_RESOLUTION.id: make_resolution()}


domain = Domain(
    name="_builtin",
    fields=FIELDS,
    capabilities=CAPABILITIES,
    build_calls=build_calls,
)
