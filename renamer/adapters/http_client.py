"""网络端口适配器：同步抓取并解析 JSON（GET/POST），失败以 Issue 描述、绝不抛异常"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from urllib.request import Request, urlopen

from renamer.core.model import Issue, Level

__all__ = ["HttpClient"]

_DEFAULT_TIMEOUT = 10.0
# Bangumi API 规则：非浏览器客户端必须带可识别的 User-Agent，否则 403
_DEFAULT_UA = "zaixiamomo/my-private-project"


def _default_fetch(
    url: str,
    method: str,
    payload: Mapping[str, object] | None,
    user_agent: str,
) -> str:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"User-Agent": user_agent}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method=method)
    with urlopen(request, timeout=_DEFAULT_TIMEOUT) as resp:
        return resp.read().decode("utf-8")


class HttpClient:
    """同步 JSON 抓取器（GET/POST），满足 HttpClient 端口协议，fetcher 可注入"""

    def __init__(
        self,
        *,
        user_agent: str = _DEFAULT_UA,
        fetcher: Callable[[str, str, Mapping[str, object] | None, str], str]
        | None = None,
    ) -> None:
        self._ua = user_agent
        self._fetch = fetcher or _default_fetch

    def get_json(
        self,
        url: str,
        *,
        method: str = "GET",
        payload: Mapping[str, object] | None = None,
    ) -> tuple[dict | None, Issue | None]:
        """抓取并解析 JSON 对象，失败降级为 Issue，绝不抛异常"""
        try:
            text = self._fetch(url, method=method, payload=payload, user_agent=self._ua)
        except Exception as exc:  # noqa: BLE001 网络层错误一律降级为 Issue
            return None, Issue(
                level=Level.WARNING,
                code="fetch_failed",
                message=f"抓取失败: {exc}",
            )
        try:
            data = json.loads(text)
        except Exception as exc:  # noqa: BLE001 解析失败降级为 Issue
            return None, Issue(
                level=Level.WARNING,
                code="fetch_failed",
                message=f"JSON 解析失败: {exc}",
            )
        if not isinstance(data, dict):
            return None, Issue(
                level=Level.WARNING,
                code="fetch_failed",
                message="响应不是 JSON 对象",
            )
        return data, None
