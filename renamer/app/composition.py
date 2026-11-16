"""组合根：装配应用服务、默认适配器和领域能力实现"""

from __future__ import annotations

from pathlib import Path

from renamer.adapters import Clock, FileSystem, HttpClient, Logger, UndoLog
from renamer.adapters.config import Config, load_config
from renamer.core.codec import toml_codec
from renamer.core.model import CapabilityFn, Issue, Level, Library, PlanError
from renamer.core.plugins import DomainRegistry
from renamer.core.ports import HttpClient as HttpClientPort
from renamer.core.ports import Logger as LoggerPort
from renamer.plugins import default_registry

from .authoring import AuthoringService
from .file_operations import FileOperations
from .service import RenameService

__all__ = [
    "build_authoring_service",
    "build_file_operations",
    "build_service",
    "capability_calls",
    "load_library",
]


def load_library(path: Path | str) -> Library:
    """从 TOML 路径读取 Library（读取失败/字段非法抛 PlanError=rule_load_failed）"""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PlanError(
            [
                Issue(
                    level=Level.ERROR,
                    code="rule_load_failed",
                    message=f"无法读取库文件 {path}: {exc}",
                )
            ]
        ) from exc
    return toml_codec.parse(text)


def build_service(
    library_path: Path | str | None = None,
    *,
    library: Library | None = None,
    config: Config | None = None,
    undo_log_path: Path | str | None = None,
    http: HttpClientPort | None = None,
    logger: LoggerPort | None = None,
    registry: DomainRegistry | None = None,
) -> RenameService:
    """装配所有真实适配器与能力，返回可用的 RenameService

    Args:
        library_path: TOML library 路径（模板 + 规则），None 用空 Library
        library: 内存 Library，优先于 library_path
        config: 注入的配置快照，未提供时加载用户配置
        undo_log_path: 显式日志路径，优先于 config；单独提供时跳过配置文件
        http: HttpClient 注入，缺省真实实现（urllib）
        logger: Logger 注入，缺省 stderr JSON 行日志
        registry: 领域注册表，未提供时使用默认插件

    Returns:
        已装配的 RenameService
    """
    config = _resolve_config(config, undo_log_path)
    operations = build_file_operations(undo_log_path, config=config, logger=logger)
    http_client = http if http is not None else HttpClient()

    if library is None:
        library = load_library(library_path) if library_path is not None else Library()
    registry = registry if registry is not None else default_registry()
    capabilities = registry.capabilities_by_id()
    calls = registry.build_calls(http_client)

    return RenameService(
        library=library,
        operations=operations,
        clock=Clock(),
        capabilities=capabilities,
        calls=calls,
    )


def build_file_operations(
    undo_log_path: Path | str | None = None,
    *,
    config: Config | None = None,
    logger: LoggerPort | None = None,
) -> FileOperations:
    """装配文件变更与撤销，不加载规则库或创建插件能力"""
    config = _resolve_config(config, undo_log_path)
    path = undo_log_path if undo_log_path is not None else config.undo_log_path
    try:
        undo_log = UndoLog(Path(path).expanduser())
        undo_log.path.parent.mkdir(parents=True, exist_ok=True)
        if undo_log.path.is_dir():
            raise IsADirectoryError("日志路径指向目录，请指定文件")
    except (OSError, ValueError, RuntimeError) as exc:
        raise PlanError(
            [
                Issue(
                    level=Level.ERROR,
                    code="undo_log_unavailable",
                    message=f"无法使用撤销日志 {path}：{exc}",
                )
            ]
        ) from exc
    return FileOperations(
        FileSystem(), undo_log, logger if logger is not None else Logger()
    )


def _resolve_config(config: Config | None, undo_log_path: Path | str | None) -> Config:
    """复用注入快照；显式日志路径可在配置文件损坏时独立使用。"""
    if config is not None:
        return config
    return Config() if undo_log_path is not None else load_config()


def build_authoring_service(
    registry: DomainRegistry | None = None,
) -> AuthoringService:
    """使用给定或默认领域注册表装配编辑服务"""
    registry = registry if registry is not None else default_registry()
    return AuthoringService(registry)


def capability_calls(
    http: HttpClientPort | None = None,
    *,
    registry: DomainRegistry | None = None,
) -> dict[str, CapabilityFn]:
    """装配给定或默认领域的能力实现，未提供 HTTP 端口时使用真实适配器"""
    registry = registry if registry is not None else default_registry()
    return registry.build_calls(http if http is not None else HttpClient())
