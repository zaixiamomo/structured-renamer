"""渠道 Channel：五个来源，固定优先级 USER、INFO、PARSE、WEB、AI"""

from __future__ import annotations

from enum import Enum


class Channel(str, Enum):
    USER = "user"
    INFO = "info"
    PARSE = "parse"
    WEB = "web"
    AI = "ai"

    @property
    def priority(self) -> int:
        """优先级序号，越大优先级越高（USER=5 最高，AI=1 最低）"""
        return _PRIORITY[self]

    def __str__(self) -> str:
        return self.value


_PRIORITY = {
    Channel.USER: 5,
    Channel.INFO: 4,
    Channel.PARSE: 3,
    Channel.WEB: 2,
    Channel.AI: 1,
}
