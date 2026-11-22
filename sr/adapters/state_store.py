import json
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from sr.app.errors import ApplicationError
from sr.app.models import Batch, Change, FileStamp, Ledger, StoredError


class LocalStateStore:
    """使用全局锁和原子写入的本地账本存储。"""

    def __init__(self, directory: Path) -> None:
        """展开并解析账本存储目录。"""
        self.directory = directory.expanduser().resolve()

    def validate_target(self, directory: Path) -> None:
        """拒绝状态目录落入改名扫描范围。

        Args:
            directory: 待改名的扫描根目录。
        Raises:
            ApplicationError: 状态目录位于扫描根目录内。
        """
        canonical = directory.resolve()
        if self.directory == canonical or self.directory.is_relative_to(canonical):
            raise ApplicationError("状态目录不能放在待改名目录内")

    @contextmanager
    def lock(self) -> Iterator[None]:
        """获取全局进程锁，覆盖读取、移动和提交。

        Yields:
            持锁期间执行调用方逻辑。
        Raises:
            ApplicationError: 另一个 sr 进程正在使用状态。
        """
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
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)

    def load(self) -> Ledger:
        """持锁读取全局账本。

        Returns:
            从状态文件恢复的账本；状态文件不存在时返回空账本。
        Raises:
            ApplicationError: 发现旧版状态或状态文件损坏。
            OSError: 状态文件无法读取。
        """
        legacy = self._legacy_path()
        if legacy is not None:
            raise ApplicationError(
                f"发现旧版目录状态：{legacy}；请使用旧版处理或备份旧状态后选择新的 SR_STATE_DIR"
            )
        path = self.directory / "state.json"
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return Ledger()
        try:
            document = json.loads(text)
            if not isinstance(document, dict):
                raise TypeError("状态文件缺少对象")
            return _decode_ledger(document.get("ledger"))
        except (ValueError, TypeError, KeyError) as exc:
            raise ApplicationError(f"状态文件损坏或格式不兼容：{path}") from exc

    def save(self, ledger: Ledger) -> None:
        """校验编码结果后原子写入 state.json。

        Args:
            ledger: 待保存的完整账本。
        Raises:
            OSError: 写入或替换失败，原状态文件保持不变。
        """
        document = {"ledger": _encode_ledger(ledger)}
        text = json.dumps(document, ensure_ascii=False, indent=2)
        _decode_ledger(document["ledger"])
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
            os.replace(temporary, self.directory / "state.json")
        finally:
            if temporary is not None:
                with suppress(OSError):
                    temporary.unlink(missing_ok=True)

    def _legacy_path(self) -> Path | None:
        """查找旧版按目录保存的 SHA-256 十六进制状态文件。"""
        return next(
            (
                p
                for p in self.directory.glob("*.json")
                if len(p.stem) == 64 and all(c in "0123456789abcdef" for c in p.stem)
            ),
            None,
        )


def _encode_ledger(ledger: Ledger) -> dict[str, object]:
    """把账本转换为 JSON 对象。"""
    return {
        "batches": [_encode_batch(batch) for batch in ledger.batches],
        "redo_stack": list(ledger.redo_stack),
    }


def _encode_batch(batch: Batch) -> dict[str, object]:
    """把批次转换为 JSON 对象。"""
    return {
        "id": batch.id,
        "dir": str(batch.dir),
        "direction": batch.direction,
        "status": batch.status,
        "updated": batch.updated.isoformat(),
        "changes": [_encode_change(change) for change in batch.changes],
    }


def _encode_change(change: Change) -> dict[str, object]:
    """把逐文件改动转换为 JSON 对象。"""
    return {
        "source": str(change.source),
        "target": None if change.target is None else str(change.target),
        "temporary": (None if change.temporary is None else str(change.temporary)),
        "stamp": {
            "parent": list(change.stamp.parent),
            "file": list(change.stamp.file),
            "size": change.stamp.size,
            "modified_ns": change.stamp.modified_ns,
        },
        "error": _encode_error(change.error),
    }


def _encode_error(error: Exception | None) -> dict[str, object] | None:
    """把异常归一为可序列化的类型、消息和文件错误信息。"""
    if error is None:
        return None
    stored = StoredError.from_error(error)
    document: dict[str, object] = {"type": stored.type_name, "message": str(stored)}
    if stored.stage is not None:
        document["stage"] = stored.stage
    if stored.cause_type is not None:
        document["cause_type"] = stored.cause_type
    return document


def _decode_ledger(value: object) -> Ledger:
    """从 JSON 对象恢复账本。"""
    data = _mapping(value, "ledger")
    batches = tuple(
        _decode_batch(item) for item in _list(data.get("batches"), "batches")
    )
    stack = tuple(
        _string(item, "redo_stack")
        for item in _list(data.get("redo_stack"), "redo_stack")
    )
    return Ledger(batches, stack)


def _decode_batch(value: object) -> Batch:
    """从 JSON 对象恢复批次。"""
    data = _mapping(value, "batch")
    return Batch(
        id=_string(data.get("id"), "id"),
        dir=Path(_string(data.get("dir"), "dir")),
        direction=_direction(data.get("direction")),
        status=_status(data.get("status")),
        updated=_datetime(data.get("updated")),
        changes=tuple(
            _decode_change(item) for item in _list(data.get("changes"), "changes")
        ),
    )


def _decode_change(value: object) -> Change:
    """从 JSON 对象恢复逐文件改动。"""
    data = _mapping(value, "change")
    return Change(
        source=Path(_string(data.get("source"), "source")),
        target=_optional_path(data.get("target"), "target"),
        temporary=_optional_path(data.get("temporary"), "temporary"),
        stamp=_decode_stamp(data.get("stamp")),
        error=_decode_error(data.get("error")),
    )


def _decode_stamp(value: object) -> FileStamp:
    """从 JSON 对象恢复文件快照。"""
    data = _mapping(value, "stamp")
    return FileStamp(
        parent=_pair(data.get("parent"), "parent"),
        file=_pair(data.get("file"), "file"),
        size=_integer(data.get("size"), "size"),
        modified_ns=_integer(data.get("modified_ns"), "modified_ns"),
    )


def _decode_error(value: object) -> StoredError | None:
    """从 JSON 对象恢复错误。"""
    if value is None:
        return None
    data = _mapping(value, "error")
    return StoredError(
        _string(data.get("type"), "error.type"),
        _text(data.get("message"), "error.message"),
        stage=_optional_text(data.get("stage"), "error.stage"),
        cause_type=_optional_text(data.get("cause_type"), "error.cause_type"),
    )


def _mapping(value: object, name: str) -> Mapping[str, object]:
    """要求对象是字符串键映射。"""
    if not isinstance(value, dict):
        raise TypeError(f"{name} 必须是对象")
    if any(not isinstance(key, str) for key in value):
        raise ValueError(f"{name} 的键必须是字符串")
    return value


def _list(value: object, name: str) -> list[object]:
    """要求值是数组。"""
    if not isinstance(value, list):
        raise TypeError(f"{name} 必须是数组")
    return value


def _string(value: object, name: str) -> str:
    """要求值是非空字符串。"""
    if not isinstance(value, str):
        raise TypeError(f"{name} 必须是字符串")
    if not value:
        raise ValueError(f"{name} 必须是非空字符串")
    return value


def _text(value: object, name: str) -> str:
    """要求值是字符串，允许为空。"""
    if not isinstance(value, str):
        raise TypeError(f"{name} 必须是字符串")
    return value


def _optional_text(value: object, name: str) -> str | None:
    """要求值是可空字符串。"""
    if value is None:
        return None
    return _text(value, name)


def _integer(value: object, name: str) -> int:
    """要求值是整数。"""
    if type(value) is not int:
        raise TypeError(f"{name} 必须是整数")
    return value


def _pair(value: object, name: str) -> tuple[int, int]:
    """要求值是两个整数。"""
    items = _list(value, name)
    if len(items) != 2:
        raise ValueError(f"{name} 必须有两个整数")
    return _integer(items[0], name), _integer(items[1], name)


def _optional_path(value: object, name: str) -> Path | None:
    """要求值是可空路径字符串。"""
    if value is None:
        return None
    return Path(_string(value, name))


def _direction(value: object) -> str:
    """校验批次方向。"""
    if value not in ("forward", "backward"):
        raise ValueError("direction 必须是 forward 或 backward")
    return value


def _status(value: object) -> str:
    """校验批次状态。"""
    if value not in ("running", "completed"):
        raise ValueError("status 必须是 running 或 completed")
    return value


def _datetime(value: object) -> datetime:
    """解析带时区的 ISO 时间。"""
    text = _string(value, "updated")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("时间必须包含时区")
    return parsed
