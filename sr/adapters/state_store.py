"""以 JSON 文件保存目录改名状态。"""

import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

from pydantic import BaseModel, ConfigDict

from sr.app.errors import ApplicationError
from sr.app.models import (
    DirectoryState,
    FileChange,
    RenameOperation,
)


class _State(BaseModel):
    """状态文件的版本化序列化模型。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    # 版本 3 为当前格式；不兼容版本在 _decode 中直接拒绝。
    version: Literal[3]
    directory: Path
    undo: tuple[FileChange, ...]
    active: RenameOperation | None

    def restore(self) -> DirectoryState:
        """转换为应用层 DirectoryState。"""
        return DirectoryState(
            directory=self.directory,
            undo=self.undo,
            active=self.active,
        )


def _decode(text: str) -> DirectoryState:
    """解析并校验状态文件文本。"""
    document = json.loads(text)
    if not isinstance(document, dict) or type(document.get("version")) is not int:
        raise ValueError("状态文件缺少有效版本")
    if document["version"] != 3:
        raise ValueError("不支持此状态文件版本")
    return _State.model_validate_json(text).restore()


class LocalStateStore:
    """带进程锁和原子写入的本地状态存储。"""

    def __init__(self, directory: Path) -> None:
        """规范化并保存状态目录路径。"""
        self.directory = directory.expanduser().resolve()

    @contextmanager
    def lock(self, directory: Path):
        """锁定状态目录并检查跨目录未完成操作。

        Args:
            directory: 当前命令要处理的目录。
        Yields:
            持锁期间执行调用方逻辑。
        Raises:
            ApplicationError: 状态目录位于待处理目录内、已有进程持锁，或存在重叠目录的未完成操作。
        """
        canonical = directory.resolve()
        if self.directory == canonical or self.directory.is_relative_to(canonical):
            raise ApplicationError("状态目录不能放在待改名目录内")
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / "state.lock").open("a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                # msvcrt 只能锁定文件中真实存在的字节。
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ApplicationError(
                    "另一个 sr 命令正在使用状态，请稍后重试"
                ) from exc
            try:
                self._check_recovery(directory)
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)

    def _path(self, directory: Path) -> Path:
        """返回目录对应的状态文件名。"""
        # 文件名取规范路径的 SHA-256，避免路径字符进入文件名。
        key = hashlib.sha256(str(directory.resolve()).encode("utf-8")).hexdigest()
        return self.directory / f"{key}.json"

    def _check_recovery(self, directory: Path) -> None:
        """拒绝重叠目录的未完成操作，并校验其他状态文件。"""
        canonical = directory.resolve()
        current = self._path(directory)
        for path in self.directory.glob("*.json"):
            if path == current:
                continue
            try:
                record = _decode(path.read_text(encoding="utf-8"))
                other = record.directory.resolve()
            except (ValueError, TypeError) as exc:
                raise ApplicationError(f"状态文件损坏或版本不兼容：{path}") from exc
            # 只阻止与未完成操作目录重叠的命令；已结算记录可以共存。
            if record.active is not None and (
                canonical.is_relative_to(other) or other.is_relative_to(canonical)
            ):
                raise ApplicationError(
                    f"重叠目录尚未恢复，请先对 {record.directory} 执行 --undo"
                )

    def load(self, directory: Path) -> DirectoryState:
        """读取目录状态。

        Returns:
            已保存的 DirectoryState；无记录时返回空状态。
        Raises:
            ApplicationError: 文件损坏、版本不兼容或目录不匹配。
        """
        path = self._path(directory)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return DirectoryState(directory)
        try:
            state = _decode(text)
            if state.directory.resolve() != directory.resolve():
                raise ValueError("状态目录不匹配")
            return state
        except (ValueError, TypeError) as exc:
            raise ApplicationError(f"状态文件损坏或版本不兼容：{path}") from exc

    def save(self, state: DirectoryState) -> None:
        """原子写入状态，避免中断产生半截 JSON。"""
        data = _State(
            version=3,
            directory=state.directory,
            undo=state.undo,
            active=state.active,
        ).model_dump(mode="json")
        text = json.dumps(data, ensure_ascii=True, indent=2)
        # 写前严格回读，确保序列化结果能被当前版本接受。
        _State.model_validate_json(text).restore()
        temporary = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.directory,
                prefix=".state-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path(state.directory))
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
