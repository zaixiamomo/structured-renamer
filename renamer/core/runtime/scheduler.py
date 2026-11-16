"""按字段候选求值，每个文件内复用能力调用结果"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum, auto

from renamer.core.compile.wire import CompiledWire
from renamer.core.model import Capability, CapabilityFn, FieldKey, Issue, Level

__all__ = ["run_capabilities"]


class _State(Enum):
    READY = auto()
    MISSING = auto()
    DEFERRED = auto()


def run_capabilities(
    wire: CompiledWire,
    seeds: Mapping[FieldKey, str],
    calls: Mapping[str, CapabilityFn],
) -> tuple[dict[FieldKey, str], list[Issue]]:
    """按需求解析字段，候选优先级与能力调用先后分别处理

    Args:
        wire: 共享静态接线，不依赖模板或渲染绑定
        seeds: 本文件初始字段值，包含解析种子与 SOURCE_PATH
        calls: 能力 id 到实现函数

    Returns:
        字段值与诊断，能力失败可回退，不中断整批文件
    """
    execution = _Execution(wire, seeds, calls)
    execution.run()
    return execution.fields, execution.issues


class _Execution:
    """单文件求值状态，字段确定后固定，不进行循环更新"""

    def __init__(
        self,
        wire: CompiledWire,
        seeds: Mapping[FieldKey, str],
        calls: Mapping[str, CapabilityFn],
    ) -> None:
        self.wire = wire
        self.fields = dict(seeds)
        self.calls = calls
        self.issues: list[Issue] = []
        self.results: dict[str, dict[FieldKey, str]] = {}
        self.finished: dict[FieldKey, _State] = {}
        self.active_fields: set[FieldKey] = set()
        self.active_calls: set[str] = set()

    def run(self) -> None:
        """其他根字段可能解开暂缓依赖，有进展时再尝试暂缓的根"""
        pending = self.wire.roots
        while pending:
            before = len(self.results), len(self.finished)
            deferred = tuple(
                field for field in pending if self.resolve(field) is _State.DEFERRED
            )
            if not deferred:
                return
            if before == (len(self.results), len(self.finished)):
                self.issues.append(
                    Issue(
                        level=Level.WARNING,
                        code="capability_dependency_cycle",
                        message="候选回退后仍有循环依赖：" + _fmt_keys(deferred),
                    )
                )
                return
            pending = deferred

    def resolve(self, field: FieldKey) -> _State:
        """依候选顺序取值，循环路径暂缓，现有种子可作为初始来源"""
        if field in self.finished:
            return self.finished[field]
        if field in self.active_fields:
            return _State.READY if field in self.fields else _State.DEFERRED

        self.active_fields.add(field)
        try:
            deferred = False
            for cid in self.wire.candidates.get(field, ()):
                result = self.invoke(cid)
                if result is None:
                    deferred = True
                elif field in result:
                    self.fields[field] = result[field]
                    self.finished[field] = _State.READY
                    return _State.READY
            if field in self.fields:
                self.finished[field] = _State.READY
                return _State.READY
            if deferred:
                return _State.DEFERRED
            self.finished[field] = _State.MISSING
            return _State.MISSING
        finally:
            self.active_fields.remove(field)

    def invoke(self, cid: str) -> dict[FieldKey, str] | None:
        """复用已调用结果，None 表示依赖暂缓而非能力调用失败"""
        if cid in self.results:
            return self.results[cid]
        if cid in self.active_calls:
            return None

        cap = self.wire.capabilities[cid]
        fn = self.calls.get(cid)
        if fn is None:
            self.issues.append(
                Issue(
                    level=Level.WARNING,
                    code="capability_missing_impl",
                    message=f"capability {cap.id!r} 无实现函数",
                )
            )
            self.results[cid] = {}
            return self.results[cid]
        self.active_calls.add(cid)
        try:
            unavailable = tuple(
                field
                for field in cap.inputs
                if self.finished.get(field) is _State.MISSING
                or (field not in self.fields and not self.wire.candidates.get(field))
            )
            if unavailable:
                return self.missing_input(cid, unavailable)
            deferred = False
            for field in cap.inputs:
                state = self.resolve(field)
                if state is _State.MISSING:
                    return self.missing_input(cid, (field,))
                deferred |= state is _State.DEFERRED
            if deferred:
                return None
            result = self.call(
                cap, fn, {field: self.fields[field] for field in cap.inputs}
            )
            self.results[cid] = result
            return result
        finally:
            self.active_calls.remove(cid)

    def missing_input(
        self, cid: str, fields: tuple[FieldKey, ...]
    ) -> dict[FieldKey, str]:
        """记录确定缺失的输入，复用该候选的失败结果"""
        self.issues.append(
            Issue(
                level=Level.WARNING,
                code="capability_missing_input",
                message=f"capability {cid!r} 输入缺失（{_fmt_keys(fields)}），跳过",
            )
        )
        self.results[cid] = {}
        return self.results[cid]

    def call(
        self, cap: Capability, fn: CapabilityFn, inputs: Mapping[FieldKey, str]
    ) -> dict[FieldKey, str]:
        """调用和规范化都在插件边界内，结果仅缓存，不提前认领其他字段"""
        try:
            result = fn(inputs)
        except Exception as exc:  # noqa: BLE001 插件信任边界
            self.issues.append(
                Issue(
                    level=Level.WARNING,
                    code="capability_exception",
                    message=f"{cap.id}: {exc}",
                )
            )
            return {}
        if isinstance(result, Issue):
            self.issues.append(result)
            return {}
        if result is None:
            return {}
        try:
            if not isinstance(result, Mapping):
                raise TypeError("返回值不是字段映射")
            normalized: dict[FieldKey, str] = {}
            for key, value in result.items():
                field = key if isinstance(key, FieldKey) else FieldKey.parse(str(key))
                if field in cap.outputs:
                    normalized[field] = str(value)
            return normalized
        except Exception as exc:  # noqa: BLE001 插件结果边界
            self.issues.append(
                Issue(
                    level=Level.WARNING,
                    code="capability_invalid_output",
                    message=f"capability {cap.id!r} 返回字段非法，忽略：{exc}",
                )
            )
            return {}


def _fmt_keys(keys: tuple[FieldKey, ...]) -> str:
    return ", ".join(str(key) for key in keys)
