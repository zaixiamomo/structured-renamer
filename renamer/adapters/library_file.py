"""会话库文件的容错读取与原子写入"""

import os
from contextlib import suppress
from pathlib import Path
from tempfile import NamedTemporaryFile

from renamer.core.codec import toml_codec
from renamer.core.model import Library, PlanError


class LibraryFile:
    def __init__(self, path: Path):
        self.path = path

    def read(self) -> Library | None:
        """文件不存在、不可读或声明非法时返回 None"""
        if not self.path.exists():
            return None
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError:
            return None
        try:
            return toml_codec.parse(text)
        except PlanError:
            return None

    def write(self, library: Library) -> None:
        """完成同目录临时文件后替换正式文件，失败时清理临时文件"""
        text = toml_codec.emit(library)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        finally:
            if temporary is not None:
                with suppress(OSError):
                    temporary.unlink(missing_ok=True)
