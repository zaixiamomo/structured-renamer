"""把字段需求和能力声明编译为有序候选，执行顺序由运行时按需决定"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from renamer.core.model import (
    SOURCE_PATH_KEY,
    Capability,
    CapabilityCall,
    Channel,
    FieldKey,
    Issue,
    Level,
    PlanError,
)

__all__ = ["CompiledWire", "compile_wire"]


@dataclass(frozen=True)
class CompiledWire:
    """接线的只读快照，能力索引的键序不代表执行顺序"""

    roots: tuple[FieldKey, ...]
    candidates: Mapping[FieldKey, tuple[str, ...]]
    capabilities: Mapping[str, Capability]

    def __post_init__(self) -> None:
        object.__setattr__(self, "roots", tuple(self.roots))
        object.__setattr__(
            self,
            "candidates",
            MappingProxyType(
                {field: tuple(chain) for field, chain in self.candidates.items()}
            ),
        )
        object.__setattr__(
            self, "capabilities", MappingProxyType(dict(self.capabilities))
        )


def compile_wire(
    *,
    required: tuple[FieldKey, ...],
    seed_fields: frozenset[FieldKey],
    aliases: Mapping[str, FieldKey],
    calls: tuple[CapabilityCall, ...],
    registry: Mapping[str, Capability],
) -> CompiledWire:
    """编译自动或手动字段候选，保留既有优先级和缺输入降级策略

    自动模式按渠道优先级和注册顺序选择候选，递归补齐输入字段；手动模式
    只采用声明的输出，按声明顺序回退，不补充未声明的能力。种子和内建
    SOURCE_PATH 都是静态来源，已有解析种子仅允许手动指定的高渠道覆盖。

    无生产者的中间输入留给运行时诊断。静态检查只拒绝即使补齐这些外部
    输入仍无法得到根字段的候选循环，不因某条可选分支存在环而拒绝计划。
    """
    by_id: dict[str, Capability] = {}
    for cap in registry.values():
        by_id.setdefault(cap.id, cap)

    issues: list[Issue] = []
    if calls:
        candidates = _manual_candidates(calls, by_id, aliases, seed_fields, issues)
        roots = tuple(dict.fromkeys((*required, *candidates)))
        capability_order = tuple(call.func for call in calls)
    else:
        ordered = sorted(by_id.values(), key=lambda cap: -cap.channel.priority)
        candidates = _auto_candidates(required, seed_fields, ordered, issues)
        roots = tuple(dict.fromkeys(required))
        capability_order = tuple(cap.id for cap in ordered)

    if issues:
        raise PlanError(issues)

    selected = {cid for chain in candidates.values() for cid in chain}
    capabilities = {cid: by_id[cid] for cid in capability_order if cid in selected}
    blocked = _cyclic_roots(roots, candidates, capabilities, seed_fields)
    if blocked:
        raise PlanError(
            [
                Issue(
                    level=Level.ERROR,
                    code="dependency_cycle",
                    message=(
                        "能力候选循环使字段无法获得初始来源："
                        + ", ".join(str(field) for field in blocked)
                    ),
                )
            ]
        )

    return CompiledWire(roots, candidates, capabilities)


def _manual_candidates(
    calls: tuple[CapabilityCall, ...],
    by_id: Mapping[str, Capability],
    aliases: Mapping[str, FieldKey],
    seed_fields: frozenset[FieldKey],
    issues: list[Issue],
) -> dict[FieldKey, tuple[str, ...]]:
    """仅接入显式输出，过滤不能覆盖解析种子的渠道"""
    candidates: dict[FieldKey, list[str]] = {}
    seen: set[str] = set()
    for call in calls:
        cap = by_id.get(call.func)
        if cap is None:
            issues.append(
                Issue(
                    level=Level.ERROR,
                    code="unknown_capability",
                    message=f"规则引用了未知能力 {call.func!r}",
                )
            )
            continue
        if call.func in seen:
            issues.append(
                Issue(
                    level=Level.ERROR,
                    code="duplicate_capability_id",
                    message=f"能力 {call.func!r} 被重复声明",
                )
            )
            continue
        seen.add(call.func)

        allowed = set(cap.outputs)
        for token in call.out:
            field = _resolve_output(token, aliases, call.func, issues)
            if field is None:
                continue
            if field not in allowed:
                issues.append(
                    Issue(
                        level=Level.ERROR,
                        code="capability_signature_mismatch",
                        message=f"能力 {call.func!r} 无法产出字段 {field}",
                    )
                )
                continue
            if field in seed_fields and cap.channel.priority <= Channel.PARSE.priority:
                continue
            chain = candidates.setdefault(field, [])
            if call.func not in chain:
                chain.append(call.func)
    return {field: tuple(chain) for field, chain in candidates.items()}


def _resolve_output(
    token: str,
    aliases: Mapping[str, FieldKey],
    cap_id: str,
    issues: list[Issue],
) -> FieldKey | None:
    """输出支持规范字段名和显式映射别名，包括未渲染的别名"""
    text = token.strip()
    if ":" in text:
        try:
            return FieldKey.parse(text)
        except ValueError as exc:
            issues.append(
                Issue(
                    level=Level.ERROR,
                    code="capability_output_unmapped",
                    message=(
                        f"能力 {cap_id!r} 的 out 字段 {text!r} 无法解析为 field key"
                        f"：{exc}"
                    ),
                )
            )
            return None
    field = aliases.get(text)
    if field is not None:
        return field
    issues.append(
        Issue(
            level=Level.ERROR,
            code="capability_output_unmapped",
            message=(
                f"能力 {cap_id!r} 的 out token {text!r} 未映射到 field key"
                f"（须为 domain:FIELD 或已显式映射的 token）"
            ),
        )
    )
    return None


def _auto_candidates(
    required: tuple[FieldKey, ...],
    seed_fields: frozenset[FieldKey],
    ordered: list[Capability],
    issues: list[Issue],
) -> dict[FieldKey, tuple[str, ...]]:
    """一次构建输出索引，再沿实际需求展开候选输入"""
    available = seed_fields | {SOURCE_PATH_KEY}
    output_index: dict[FieldKey, list[Capability]] = {}
    for cap in ordered:
        for field in dict.fromkeys(cap.outputs):
            output_index.setdefault(field, []).append(cap)

    missing_required = set(required) - available
    queue = deque(field for field in dict.fromkeys(required) if field not in available)
    queued = set(queue)
    candidates: dict[FieldKey, tuple[str, ...]] = {}
    while queue:
        field = queue.popleft()
        chain = output_index.get(field, ())
        if not chain:
            if field in missing_required:
                issues.append(
                    Issue(
                        level=Level.ERROR,
                        code="required_unfillable",
                        message=f"required 字段 {field} 无法被静态来源或能力填充",
                    )
                )
            continue

        candidates[field] = tuple(cap.id for cap in chain)
        for cap in chain:
            for field_input in cap.inputs:
                if field_input not in available and field_input not in queued:
                    queue.append(field_input)
                    queued.add(field_input)
    return candidates


def _cyclic_roots(
    roots: tuple[FieldKey, ...],
    candidates: Mapping[FieldKey, tuple[str, ...]],
    capabilities: Mapping[str, Capability],
    seed_fields: frozenset[FieldKey],
) -> tuple[FieldKey, ...]:
    """假定无生产者输入可用，仍不能达到的根字段才属于封闭候选循环"""
    fields = set(roots) | set(candidates)
    fields.update(field for cap in capabilities.values() for field in cap.inputs)
    available = set(seed_fields) | {SOURCE_PATH_KEY} | (fields - candidates.keys())
    pending = dict(candidates)
    while pending:
        added = [
            field
            for field, chain in pending.items()
            if field in available
            or any(
                all(inp in available for inp in capabilities[cid].inputs)
                for cid in chain
            )
        ]
        if not added:
            break
        available.update(added)
        for field in added:
            del pending[field]
    return tuple(field for field in roots if field not in available)
