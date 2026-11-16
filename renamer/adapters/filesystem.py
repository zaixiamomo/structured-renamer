"""文件系统端口适配器：改名原语与 exists 查询"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from renamer.core.ports import is_case_only_change

__all__ = ["FileSystem", "apply_rename", "is_case_only_change"]


def _temp_for(src: Path) -> Path:
    """为大小写两步改名生成同目录确定性的临时名，冲突时加序号"""
    base = f".{src.name}.tmp"
    candidate = src.with_name(base)
    i = 1
    while candidate.exists():
        candidate = src.with_name(f"{base}.{i}")
        i += 1
    return candidate


def apply_rename(rename: Callable[[Path, Path], None], src: Path, dst: Path) -> None:
    """执行一次改名，仅大小写不同时自动走两步改名

    Args:
        rename: 底层改名原语，默认 os.rename
        src: 源路径
        dst: 目标路径
    """
    if not is_case_only_change(src, dst):
        rename(src, dst)
        return

    tmp = _temp_for(src)
    rename(src, tmp)
    try:
        rename(tmp, dst)
    except OSError:
        # 第二步失败尽量回滚到源名，避免文件停留在临时名
        try:
            rename(tmp, src)
        except OSError:
            pass
        raise


class FileSystem:
    """基于 os 的文件系统实现，满足 FileSystem 端口协议"""

    def __init__(self, rename: Callable[[Path, Path], None] | None = None) -> None:
        """构建实现，rename 默认 os.rename，可注入"""
        self._rename = rename or os.rename

    def rename(self, src: Path, dst: Path) -> None:
        """重命名文件，目标已存在视为冲突、不覆盖"""
        src = Path(src)
        dst = Path(dst)
        if not is_case_only_change(src, dst) and dst.exists():
            raise FileExistsError(f"目标已存在，拒绝覆盖：{dst}")
        apply_rename(self._rename, src, dst)

    def exists(self, path: Path) -> bool:
        """判断路径是否存在"""
        return Path(path).exists()
