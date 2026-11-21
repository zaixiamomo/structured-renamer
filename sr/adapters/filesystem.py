"""基于本地文件系统的 FileSystem 实现。"""

import ctypes
import errno
import os
import stat
import sys
from functools import lru_cache
from pathlib import Path

from sr.app.models import FileStamp


def _is_link(info: os.stat_result) -> bool:
    """判断 stat 结果是否指向符号链接或 Windows 重解析点。"""
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _directory_id(path: Path) -> tuple[int, int]:
    """返回普通目录的 (设备号, inode)，拒绝链接。"""
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or _is_link(info):
        raise ValueError(f"目录必须是普通目录：{path}")
    if not info.st_ino:
        raise OSError("文件系统未提供可靠的目录身份")
    return info.st_dev, info.st_ino


@lru_cache(maxsize=4096)
def _windows_name_key(name: str) -> str:
    """按 Windows 大小写折叠规则生成文件名比较键。"""
    # NTFS 使用 RtlUpcaseUnicodeChar 折叠大小写，Python lower 在个别字符上并不等价。
    upcase = ctypes.WinDLL("ntdll").RtlUpcaseUnicodeChar
    upcase.argtypes = [ctypes.c_ushort]
    upcase.restype = ctypes.c_ushort
    # 目录扫描会反复询问同一名称，按 UTF-16 码元转换并缓存结果。
    encoded = name.encode("utf-16-le", errors="surrogatepass")
    mapped = b"".join(
        upcase(int.from_bytes(encoded[i : i + 2], "little")).to_bytes(2, "little")
        for i in range(0, len(encoded), 2)
    )
    return mapped.decode("utf-16-le", errors="surrogatepass")


def _case_sensitive(directory: Path) -> bool:
    """查询目录是否启用大小写敏感。"""
    if os.name != "nt":
        # PC_CASE_SENSITIVE 不是所有平台都暴露，缺失时按大小写敏感处理。
        if "PC_CASE_SENSITIVE" in os.pathconf_names:
            return bool(os.pathconf(directory, "PC_CASE_SENSITIVE"))
        if sys.platform == "darwin":
            raise OSError("当前尚不支持查询此文件系统的目录大小写规则")
        return True

    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create.restype = wintypes.HANDLE
    query = kernel.GetFileInformationByHandleEx
    query.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    query.restype = wintypes.BOOL
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    # 0=无访问权限，7=共享读写删除，3=OPEN_EXISTING，
    # 0x02000000=FILE_FLAG_BACKUP_SEMANTICS，用于打开目录句柄。
    handle = create(str(directory), 0, 7, None, 3, 0x02000000, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        flags = wintypes.DWORD()
        # 23=FileCaseSensitiveInfo；flags 的 1=FILE_CS_FLAG_CASE_SENSITIVE_DIR。
        if query(handle, 23, ctypes.byref(flags), ctypes.sizeof(flags)):
            return bool(flags.value & 1)
        # 1=ERROR_INVALID_FUNCTION，50=ERROR_NOT_SUPPORTED，
        # 87=ERROR_INVALID_PARAMETER：文件系统不支持该查询，按大小写不敏感处理。
        if ctypes.get_last_error() in (1, 50, 87):
            return False
        raise ctypes.WinError(ctypes.get_last_error())
    finally:
        close(handle)


class LocalFileSystem:
    """通过 os 和 ctypes 访问本地文件。"""

    def read(self, path: Path) -> str:
        """以 UTF-8 读取文本，兼容 BOM。"""
        return path.read_text(encoding="utf-8-sig")

    def resolve(self, directory: Path) -> Path:
        """校验并规范化目录路径。"""
        _directory_id(directory)
        return directory.resolve()

    def scan(
        self, directory: Path, excluded: tuple[Path, ...] = ()
    ) -> tuple[Path, ...]:
        """递归扫描目录中的普通文件。

        Args:
            directory: 起始目录，必须是普通目录。
            excluded: 需要从结果中排除的文件路径。
        Returns:
            按路径字符串排序的文件元组；跳过链接和特殊文件。
        """
        _directory_id(directory)
        # 排除键与 key() 使用同一大小写规则。
        excluded_keys = {self.key(path) for path in excluded}
        files: list[Path] = []
        # 用显式栈遍历，避免深目录触发递归上限。
        pending = [directory]
        while pending:
            parent = pending.pop()
            _directory_id(parent)
            with os.scandir(parent) as entries:
                for entry in entries:
                    info = entry.stat(follow_symlinks=False)
                    if _is_link(info):
                        continue
                    path = Path(entry.path)
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(path)
                    elif (
                        stat.S_ISREG(info.st_mode)
                        and self.key(path) not in excluded_keys
                    ):
                        files.append(path)
        return tuple(sorted(files, key=str))

    def stat(self, path: Path) -> FileStamp:
        """采集用于检测文件变化的身份与时间戳。"""
        parent = _directory_id(path.parent)
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or _is_link(info):
            raise ValueError(f"源路径必须是普通文件：{path}")
        if not info.st_ino:
            raise OSError("文件系统未提供可靠的文件身份")
        return FileStamp(
            parent, (info.st_dev, info.st_ino), info.st_size, info.st_mtime_ns
        )

    def key(self, path: Path) -> tuple[int, int, str]:
        """返回用于判重的 (父目录标识, 大小写折叠名称)。"""
        parent = _directory_id(path.parent)
        name = path.name
        if not _case_sensitive(path.parent):
            name = _windows_name_key(name)
        return *parent, name

    def exists(self, path: Path) -> bool:
        """判断路径是否被任何对象占用（含失效链接）。"""
        return os.path.lexists(path)

    def rename(self, source: Path, target: Path) -> None:
        """原子且不覆盖地重命名同目录文件。

        Args:
            source: 当前路径。
            target: 目标路径，必须与 source 同目录。
        Raises:
            ValueError: 跨目录改名。
            FileExistsError: target 已存在。
            OSError: 平台不支持或底层调用失败。
        """
        if source.parent != target.parent:
            raise ValueError("只允许同目录改名")
        if os.name == "nt":
            # Windows 的 os.rename 在目标存在时失败，满足不覆盖要求。
            os.rename(source, target)
            return
        libc = ctypes.CDLL(None, use_errno=True)
        # 1=RENAME_NOREPLACE；-100=AT_FDCWD，表示相对当前工作目录。
        if sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
            rename = libc.renameat2
            rename.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            rename.restype = ctypes.c_int
            result = rename(-100, os.fsencode(source), -100, os.fsencode(target), 1)
        else:
            # macOS 等平台没有 renameat2，直接拒绝，避免退化为可覆盖改名。
            raise OSError(errno.ENOTSUP, "当前平台不支持原子、不覆盖的文件改名")
        if result != 0:
            number = ctypes.get_errno()
            raise OSError(number, os.strerror(number), str(target))
