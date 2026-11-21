"""带缓存和按源限流的 JSON HTTP 客户端。"""

import json
import math
from collections.abc import Mapping
from concurrent.futures import Future
from copy import copy, deepcopy
from http.client import HTTPException
from threading import Lock
from time import monotonic, sleep
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class _Endpoint:
    """记录单个来源的限流状态。"""

    def __init__(self) -> None:
        """初始化来源锁与起始时间。"""
        self.lock = Lock()
        self.started: float | None = None


class JsonHttpClient:
    """提供同批次请求去重、结果缓存和按源限流的 JSON POST。"""

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        user_agent: str = "",
        min_interval: float = 1.0,
    ) -> None:
        """配置客户端。

        Args:
            timeout: 单次请求超时秒数，必须是有限正数。
            user_agent: 非空单行 User-Agent。
            min_interval: 同一来源两次请求的最小间隔秒数。
        Raises:
            ValueError: 任一参数非法。
        """
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("HTTP 超时必须是有限正数")
        if not user_agent.strip() or "\r" in user_agent or "\n" in user_agent:
            raise ValueError("HTTP User-Agent 必须为非空单行文本")
        if not math.isfinite(min_interval) or min_interval <= 0:
            raise ValueError("HTTP 查询间隔必须是有限正数")
        self._timeout = timeout
        self._user_agent = user_agent
        self._min_interval = min_interval
        self._cache: dict[tuple[str, bytes], Future[object]] = {}
        self._cache_lock = Lock()
        self._endpoints: dict[tuple[str, str | None, int | None], _Endpoint] = {}
        self._endpoints_lock = Lock()

    def new_batch(self) -> "JsonHttpClient":
        """创建共享限流状态、使用独立缓存的新客户端。"""
        client = copy(self)
        client._cache = {}
        client._cache_lock = Lock()
        return client

    def post_json(self, url: str, *, payload: Mapping[str, object]) -> object:
        """发送 JSON POST，并复用同一批次内的相同请求。

        Args:
            url: 目标 http(s) 地址。
            payload: 请求体映射，按键排序序列化。
        Returns:
            反序列化后的响应副本。
        Raises:
            OSError: 网络失败。
            HTTPException: HTTP 协议错误。
            ValueError: 响应不是合法 JSON。
        """
        body = json.dumps(
            dict(payload), ensure_ascii=False, sort_keys=True, allow_nan=False
        ).encode("utf-8")
        key = (url, body)
        with self._cache_lock:
            future = self._cache.get(key)
            owner = future is None
            if owner:
                # 先占位，让并发的相同请求等待同一个结果。
                future = Future()
                self._cache[key] = future
        if owner:
            try:
                self._wait_for_start(url)
                result = self._request(url, body)
            except BaseException as exc:
                with self._cache_lock:
                    # 可预期的失败留在缓存中，避免同批次重复请求；其余错误删除以允许重试。
                    if not isinstance(exc, (OSError, HTTPException, ValueError)):
                        del self._cache[key]
                    future.set_exception(exc)
                raise
            else:
                future.set_result(result)
        return deepcopy(future.result())

    def _wait_for_start(self, url: str) -> None:
        """等待同一来源达到最小请求间隔。"""
        parts = urlsplit(url)
        port = parts.port
        origin = (
            parts.scheme.lower(),
            parts.hostname,
            port
            if port is not None
            else {"http": 80, "https": 443}.get(parts.scheme.lower()),
        )
        with self._endpoints_lock:
            endpoint = self._endpoints.setdefault(origin, _Endpoint())
        # 每个来源独立加锁，不同来源的请求可以并行。
        with endpoint.lock:
            if endpoint.started is not None:
                remaining = endpoint.started + self._min_interval - monotonic()
                while remaining > 0:
                    sleep(remaining)
                    remaining = endpoint.started + self._min_interval - monotonic()
            endpoint.started = monotonic()

    def _request(self, url: str, body: bytes) -> object:
        """执行一次 POST 并解析 JSON 响应。"""
        request = Request(
            url,
            data=body,
            headers={
                "User-Agent": self._user_agent,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=self._timeout) as response:
            return json.loads(response.read().decode("utf-8"))
