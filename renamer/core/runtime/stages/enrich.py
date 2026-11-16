from __future__ import annotations

from collections.abc import Mapping

from renamer.core.compile.wire import CompiledWire
from renamer.core.model import CapabilityFn

from ..context import Context
from ..scheduler import run_capabilities
from ..stage import parse_mismatched


class EnrichStage:
    """以当前 fields 为种子求值能力，回写字段并累积诊断"""

    name = "enrich"

    def __init__(self, wire: CompiledWire, calls: Mapping[str, CapabilityFn]) -> None:
        self._wire = wire
        self._calls = calls

    def process(self, ctx: Context) -> None:
        if parse_mismatched(ctx):
            return
        fields, issues = run_capabilities(self._wire, ctx.fields, self._calls)
        ctx.fields = fields
        ctx.issues.extend(issues)
