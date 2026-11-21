"""拓展能力可用的外部资源。"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Protocol, runtime_checkable


class HttpClient(Protocol):
    """JSON HTTP 客户端契约。"""

    def post_json(self, url: str, *, payload: Mapping[str, object]) -> object:
        """发送 JSON POST 并返回解析后的响应。

        Args:
            url: 完整的 http(s) 地址。
            payload: 可 JSON 序列化的映射；NaN/Infinity 会被拒绝。
        Returns:
            反序列化后的响应对象；每次返回独立副本。
        Raises:
            OSError: 网络失败。
            HTTPException: HTTP 协议错误。
            ValueError: 响应不是合法 JSON。
        """
        ...


@runtime_checkable
class BatchHttpClient(HttpClient, Protocol):
    """可按批次复用限流状态的 HTTP 客户端。"""

    def new_batch(self) -> HttpClient:
        """创建供单批请求使用的新 HttpClient。"""
        ...


class MediaProbe(Protocol):
    """媒体探测客户端契约。"""

    def probe(self, path: str) -> object:
        """探测媒体文件的流信息。

        Args:
            path: 待探测文件的路径字符串。
        Returns:
            解析后的 ffprobe JSON 对象。
        Raises:
            OSError: 无法启动探测进程。
            subprocess.CalledProcessError: 探测进程返回非零。
            ValueError: 输出不是合法 JSON。
        """
        ...


# 资源名到实例的只读映射。
ResourceValues = Mapping[str, HttpClient | MediaProbe]


@dataclass(frozen=True)
class ExtenderResources:
    """按需提供给拓展的外部资源集合。"""

    http: HttpClient | None = None
    media: MediaProbe | None = None

    def select(self, required: tuple[str, ...]) -> ResourceValues:
        """按声明挑选资源。

        Args:
            required: Extender.required_resources 声明的资源名元组。
        Returns:
            资源名到实例的只读映射。
        Raises:
            ValueError: 名称非法或所需资源未配置。
        """
        check_required_resources(required)
        selected = {}
        for name in required:
            resource = getattr(self, name)
            if resource is None:
                raise ValueError(f"能力资源未配置：{name}")
            selected[name] = resource
        return MappingProxyType(selected)

    def for_batch(self) -> "ExtenderResources":
        """为一批请求准备资源。

        Returns:
            若 http 支持 new_batch，则返回带独立缓存的副本；否则返回自身。
        """
        if isinstance(self.http, BatchHttpClient):
            return replace(self, http=self.http.new_batch())
        return self


def check_required_resources(names: tuple[str, ...]) -> None:
    """校验 required_resources 声明。

    Args:
        names: 只包含 http、media 且无重复项的元组。
    Raises:
        ValueError: 容器类型、资源名称或唯一性不符合要求。
    """
    if (
        not isinstance(names, tuple)
        or any(
            not isinstance(name, str) or name not in ("http", "media") for name in names
        )
        or len(names) != len(set(names))
    ):
        raise ValueError("required_resources 必须是不重复的 http/media 资源名称元组")
