"""字段模型：FieldType、FieldKey、Field"""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

_DOMAIN_RE = re.compile(r"[a-z0-9_]+")
_FIELD_RE = re.compile(r"[A-Z0-9_]+")


class FieldType(str, Enum):
    STRING = "string"
    INT = "int"
    DATE = "date"
    ENUM = "enum"


class FieldKey(BaseModel):
    """规范字段 key：domain:FIELD 命名空间形式，可哈希可比较，可直接作 dict key"""

    domain: str
    field: str

    model_config = ConfigDict(frozen=True)

    @field_validator("domain")
    @classmethod
    def _validate_domain(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if not _DOMAIN_RE.fullmatch(v):
            raise ValueError(f"非法 domain {v!r}：应为 [a-z0-9_]+（小写）")
        return v

    @field_validator("field")
    @classmethod
    def _validate_field(cls, v: str) -> str:
        v = (v or "").strip().upper()
        if not _FIELD_RE.fullmatch(v):
            raise ValueError(f"非法 field {v!r}：应为 [A-Z0-9_]+（大写）")
        return v

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data):
        """允许以 domain:FIELD 字符串直接构造"""
        if isinstance(data, str):
            return cls._split(data)
        return data

    @classmethod
    def parse(cls, value: str) -> FieldKey:
        """解析 domain:FIELD 字符串为 FieldKey

        Args:
            value: 形如 domain:FIELD 的字符串

        Returns:
            解析得到的 FieldKey

        Raises:
            ValueError: 格式非法
        """
        return cls(**cls._split(value))

    @staticmethod
    def _split(value: str) -> dict[str, str]:
        text = (value or "").strip()
        if ":" not in text:
            raise ValueError(
                f"非法 FieldKey {value!r}：缺少 ':'（应为 'domain:FIELD'）"
            )
        domain, _, field = text.partition(":")
        return {"domain": domain, "field": field}

    def __str__(self) -> str:
        return f"{self.domain}:{self.field}"

    def __repr__(self) -> str:
        return f"FieldKey({str(self)!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FieldKey):
            return (self.domain, self.field) == (other.domain, other.field)
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.domain, self.field))

    def __lt__(self, other: object) -> bool:
        if isinstance(other, FieldKey):
            return (self.domain, self.field) < (other.domain, other.field)
        return NotImplemented


SOURCE_PATH_KEY = FieldKey.parse("_builtin:SOURCE_PATH")


class Field(BaseModel):
    """字段声明：仅规范 key 与类型"""

    key: FieldKey
    type: FieldType = FieldType.STRING

    model_config = ConfigDict(frozen=True)
