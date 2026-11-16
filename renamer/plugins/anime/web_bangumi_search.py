"""WEB 渠道：Bangumi 信息搜索能力，内嵌于 anime 领域（v0 search 单次请求）"""

from __future__ import annotations

from collections.abc import Mapping
from difflib import SequenceMatcher

from renamer.core.model import (
    Capability,
    CapabilityFn,
    CapabilityResult,
    Channel,
    FieldKey,
    Issue,
    Level,
)
from renamer.core.ports import HttpClient

__all__ = ["CAPABILITY", "make_bangumi_search"]

_TITLE = FieldKey.parse("anime:TITLE")
_DATE = FieldKey.parse("anime:DATE")
_NAME_CN = FieldKey.parse("anime:NAME_CN")

_SEARCH_URL = "https://api.bgm.tv/v0/search/subjects"
_ANIME_TYPE = 2  # Bangumi subject type=2 动画

CAPABILITY = Capability(
    id="web.anime.bangumi_search",
    channel=Channel.WEB,
    inputs=(_TITLE,),
    outputs=(_DATE, _NAME_CN),
    description="以标题一次搜索 Bangumi 条目，返回放送日期与中文名",
)


def make_bangumi_search(http: HttpClient | None) -> CapabilityFn:
    """构造 bangumi_search 能力实现，注入 HttpClient，未注入时返回 None（未配置）"""
    cache: dict[str, CapabilityResult] = {}

    def bangumi_search(inputs: Mapping[FieldKey, str]) -> CapabilityResult:
        title = inputs.get(_TITLE)
        if not title:
            return None
        if http is None:
            return None
        if title in cache:
            return cache[title]
        try:
            result = _search_fields(title, http)
        except Exception as exc:  # noqa: BLE001 能力信任边界，异常降级 Issue
            result = Issue(
                level=Level.WARNING,
                code="capability_exception",
                message=f"web.anime.bangumi_search: {exc}",
            )
        cache[title] = result
        return result

    return bangumi_search


# 纯函数：请求体构造、响应候选、标题消歧、字段提取


def _payload(title: str) -> dict[str, object]:
    return {"keyword": title, "filter": {"type": [_ANIME_TYPE]}}


def _candidates(data: object) -> list[Mapping[str, object]]:
    """从 v0 search 响应提取候选列表（{"data": [...]}）"""
    if not isinstance(data, Mapping):
        return []
    items = data.get("data")
    if not isinstance(items, list):
        return []
    return [c for c in items if isinstance(c, Mapping)]


def _norm(text: str) -> str:
    """归一化标题：小写并去除空白，用于相似度比较"""
    return "".join((text or "").lower().split())


def _similarity(query: str, candidate: Mapping[str, object]) -> float:
    """候选与查询标题的相似度，取 name / name_cn 中较接近者"""
    target = _norm(query)
    if not target:
        return 0.0
    best = 0.0
    for key in ("name", "name_cn"):
        value = candidate.get(key)
        if not isinstance(value, str):
            continue
        norm = _norm(value)
        if not norm:
            continue
        if norm == target:
            return 1.0
        best = max(best, SequenceMatcher(None, target, norm).ratio())
    return best


def _pick(data: object, title: str) -> dict[FieldKey, str] | None:
    """选放送日期候选：优先标题相似度最高者；全无文本相似时信任搜索排序取首个

    Bangumi 的 name/name_cn 是日/中文，罗马音或译名查询可能零文本相似，
    此时按 v0 搜索自身的相关性排序兜底（首个带日期的候选）。
    """
    best_candidate: Mapping[str, object] | None = None
    best_score = -1.0  # 允许 0 相似度的候选进入，作为搜索排序兜底
    for candidate in _candidates(data):
        date = candidate.get("date")
        if not isinstance(date, str) or not date:
            continue
        score = _similarity(title, candidate)
        if score > best_score:
            best_score = score
            best_candidate = candidate
    if best_candidate is None:
        return None
    out: dict[FieldKey, str] = {}
    date = best_candidate.get("date")
    if isinstance(date, str) and date:
        out[_DATE] = date
    name_cn = best_candidate.get("name_cn")
    if isinstance(name_cn, str) and name_cn:
        out[_NAME_CN] = name_cn
    return out or None


def _search_fields(title: str, getter: HttpClient) -> CapabilityResult:
    """单次搜索拿候选并消歧；网络失败回 Issue，无结果回 None"""
    data, issue = getter.get_json(_SEARCH_URL, method="POST", payload=_payload(title))
    if issue is not None:
        return issue
    return _pick(data, title)
