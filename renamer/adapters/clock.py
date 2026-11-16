"""时间端口适配器：返回 Unix 时间戳（秒），时钟可注入"""

from __future__ import annotations

import time
from collections.abc import Callable

__all__ = ["Clock"]


class Clock:
    """满足 Clock 端口协议的可注入时钟，默认 time.time"""

    def __init__(self, now: Callable[[], float] | None = None) -> None:
        self._now = now or time.time

    def __call__(self) -> float:
        return self._now()
