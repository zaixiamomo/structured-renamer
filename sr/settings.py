"""运行配置与默认状态目录。"""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sr import __version__


def default_state_directory() -> Path:
    """按平台返回状态目录，SR_STATE_DIR 优先。"""
    if override := os.environ.get("SR_STATE_DIR"):
        return Path(override)
    if os.name == "nt":
        return (
            Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
            / "structured-renamer"
        )
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/structured-renamer"
    return (
        Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
        / "structured-renamer"
    )


@dataclass(frozen=True)
class Settings:
    """一次进程使用的不可变运行配置。"""

    state_dir: Path = field(default_factory=default_state_directory)
    http_timeout: float = 10.0
    http_user_agent: str = (
        f"structured-renamer/{__version__} "
        "(+https://github.com/zaixiamomo/structured-renamer)"
    )
    http_min_interval: float = 1.0
    ffprobe_executable: str = "ffprobe"
    ffprobe_timeout: float = 10.0
    max_workers: int = 8
