"""调用 ffprobe 探测媒体信息。"""

import json
import math
import subprocess
from pathlib import Path


class FfprobeClient:
    """通过子进程读取 ffprobe 的 JSON 输出。"""

    def __init__(self, *, executable: str = "ffprobe", timeout: float = 10.0) -> None:
        """配置探测客户端。

        Args:
            executable: ffprobe 可执行文件名或路径。
            timeout: 单次探测超时秒数。
        Raises:
            ValueError: 可执行文件为空或超时非正。
        """
        if not isinstance(executable, str) or not executable.strip():
            raise ValueError("ffprobe 可执行文件不能为空")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("ffprobe 超时必须是有限正数")
        self._executable = executable
        self._timeout = timeout

    def probe(self, path: str) -> object:
        """探测文件的视频流信息。

        Args:
            path: 文件路径字符串，空值会被拒绝。
        Returns:
            包含所选视频流字段的 ffprobe JSON 对象。
        Raises:
            ValueError: path 为空或输出不是合法 JSON。
            subprocess.CalledProcessError: ffprobe 返回非零。
            subprocess.TimeoutExpired: 探测超时。
        """
        if type(path) is not str or not path.strip():
            raise ValueError("分辨率探测需要非空文件路径")
        result = subprocess.run(
            [
                self._executable,
                "-v",
                "error",
                "-print_format",
                "json",
                # V 只选普通视频流，排除封面图等附加画面。
                "-select_streams",
                "V",
                "-show_entries",
                "stream=codec_type,width,height",
                "-i",
                str(Path(path).absolute()),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            check=True,
            timeout=self._timeout,
            # 避免 Windows 弹出控制台窗口。
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return json.loads(result.stdout)
