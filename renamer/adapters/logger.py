"""结构化日志端口适配器：把事件序列化为 JSON 行写到注入的流（默认 stderr）"""

from __future__ import annotations

import json
import sys
from typing import TextIO

__all__ = ["Logger"]


class Logger:
    """满足 Logger 端口协议的 JSON 行日志器，流可注入"""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream or sys.stderr

    def log(self, event: dict) -> None:
        self._stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        self._stream.flush()
