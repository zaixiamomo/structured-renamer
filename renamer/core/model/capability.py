"""能力 Capability：以规范字段 key 为签名的注册函数"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, field_validator

from .channel import Channel
from .field import FieldKey
from .issue import Issue


class Capability(BaseModel):
    id: str
    channel: Channel
    inputs: tuple[FieldKey, ...] = ()
    outputs: tuple[FieldKey, ...] = ()
    description: str = ""
    implemented: bool = True  # False = 占位实现（无真实后端），GUI 能力列表不展示

    model_config = ConfigDict(frozen=True)

    @field_validator("channel")
    @classmethod
    def _validate_channel(cls, v: Channel) -> Channel:
        if v not in (Channel.INFO, Channel.WEB, Channel.AI):
            raise ValueError(f"capability channel 只能是 INFO/WEB/AI，得到 {v!r}")
        return v


CapabilityResult: TypeAlias = Mapping[FieldKey, str] | Issue | None
CapabilityFn: TypeAlias = Callable[[Mapping[FieldKey, str]], CapabilityResult]
