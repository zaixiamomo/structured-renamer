"""用户 TOML 配置：读取校验，首次使用时从模型默认值创建文件。"""

from contextlib import suppress
from pathlib import Path
from typing import Any

import tomli_w
from pydantic import (
    BaseModel,
    ConfigDict,
    SerializerFunctionWrapHandler,
    field_serializer,
    field_validator,
)

try:  # Python 3.11+
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib

from renamer.core.model import Issue, Level, PlanError

__all__ = ["Config", "load_config"]

_CONFIG_PATH = Path("userdata") / "config.toml"


class Config(BaseModel):
    """一次装配使用的用户配置快照，集中声明字段、默认值与校验。"""

    library_path: Path = Path("userdata") / "library.toml"
    undo_log_path: Path = Path("logs") / "undo_log.jsonl"

    model_config = ConfigDict(frozen=True, extra="forbid", validate_default=True)

    @field_validator("library_path", "undo_log_path", mode="before")
    @classmethod
    def _validate_path(cls, value: object) -> Path:
        if (
            not isinstance(value, (str, Path))
            or not str(value).strip()
            or "\0" in str(value)
        ):
            raise ValueError("必须是非空路径字符串，且不能包含空字符")
        return Path(value).expanduser()

    @field_serializer("*", mode="wrap", when_used="json")
    def _serialize_path(
        self, value: object, handler: SerializerFunctionWrapHandler
    ) -> Any:
        """持久化路径统一使用 /，其他字段保留其默认序列化行为。"""
        return value.as_posix() if isinstance(value, Path) else handler(value)


def load_config(config_path: Path | str = _CONFIG_PATH) -> Config:
    """文件缺失时创建默认配置；已有文件只读，缺失字段由模型补齐。"""
    path = Path(config_path)
    try:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            _create_default_config(path)
            text = path.read_text(encoding="utf-8-sig")
        return Config.model_validate(tomllib.loads(text))
    except (OSError, ValueError, RuntimeError) as exc:
        raise PlanError(
            [
                Issue(
                    level=Level.ERROR,
                    code="config_load_failed",
                    message=f"无法读取配置文件 {path}：{exc}",
                )
            ]
        ) from exc


def _create_default_config(path: Path) -> None:
    """序列化所有默认字段，独占创建以保留其他进程先创建的文件。"""
    created = False
    try:
        text = tomli_w.dumps(Config().model_dump(mode="json"))
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            stream = path.open("x", encoding="utf-8", newline="\n")
        except FileExistsError:
            return
        created = True
        with stream:
            stream.write(text)
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        if created:
            with suppress(OSError):
                path.unlink()
        raise PlanError(
            [
                Issue(
                    level=Level.ERROR,
                    code="config_write_failed",
                    message=f"无法创建配置文件 {path}：{exc}",
                )
            ]
        ) from exc
