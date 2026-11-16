"""INFO 渠道：file_resolution 能力，从 mkv 原始路径读取主视频分辨率（ffprobe）

一个文件即一个能力：能力元数据、ffprobe 分辨率探测与实现工厂都收在这里。
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

from renamer.core.model import (
    SOURCE_PATH_KEY,
    Capability,
    CapabilityFn,
    CapabilityResult,
    Channel,
    FieldKey,
    Issue,
    Level,
)

__all__ = ["CAPABILITY", "Probe", "Runner", "make_resolution", "probe"]

_SOURCE_PATH = SOURCE_PATH_KEY
_RESOLUTION = FieldKey.parse("_builtin:RESOLUTION")

_FFPROBE = "ffprobe"

# 探测结果键名到规范字段 key 的映射
_OUTPUTS: tuple[tuple[str, FieldKey], ...] = (("resolution", _RESOLUTION),)

# 媒体元数据探测函数：路径字符串到键值元数据的映射
Probe = Callable[[str], Mapping[str, str]]
# ffprobe 命令行执行函数（测试注入用）
Runner = Callable[[list[str]], str]

CAPABILITY = Capability(
    id="info._builtin.file_resolution",
    channel=Channel.INFO,
    inputs=(_SOURCE_PATH,),
    outputs=tuple(key for _, key in _OUTPUTS),
    description="读取 mkv 文件原始路径的主视频分辨率，无需网络",
)


def _run_ffprobe(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def probe(path: str | Path, *, runner: Runner | None = None) -> dict[str, str]:
    """读取 mkv 主视频流分辨率，只产出 {"resolution": "WxH"}，读不到返回 {}"""
    run = runner or _run_ffprobe
    text = run(
        [
            _FFPROBE,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            str(path),
        ]
    )
    data = json.loads(text)
    resolution = _resolution(data)
    return {"resolution": resolution} if resolution else {}


def _resolution(data: object) -> str | None:
    """取首个带宽高的视频流，返回 WxH；无则 None"""
    if not isinstance(data, Mapping) or not isinstance(data.get("streams"), list):
        return None
    for stream in data["streams"]:
        if not isinstance(stream, Mapping) or stream.get("codec_type") != "video":
            continue
        width = stream.get("width")
        height = stream.get("height")
        if isinstance(width, int) and isinstance(height, int):
            return f"{width}x{height}"
    return None


def make_resolution(probe: Probe = probe) -> CapabilityFn:
    """构造 file_resolution 能力实现，probe 可注入以隔离 ffprobe（测试打桩）"""

    def file_resolution(inputs: Mapping[FieldKey, str]) -> CapabilityResult:
        source = inputs.get(_SOURCE_PATH)
        if not source:
            return None
        try:
            data = probe(source)
        except Exception as exc:  # noqa: BLE001 能力信任边界，异常降级 Issue
            return Issue(
                level=Level.WARNING,
                code="capability_exception",
                message=f"info._builtin.file_resolution: {exc}",
            )
        out: dict[FieldKey, str] = {}
        for name, key in _OUTPUTS:
            value = data.get(name)
            if value is not None:
                out[key] = str(value)
        return out or None

    return file_resolution
