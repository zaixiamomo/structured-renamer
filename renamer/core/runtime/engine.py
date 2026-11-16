"""单文件执行引擎：给定 Plan、source、calls 与 fs，运行默认管线产出 FileResult"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from renamer.core.compile import Plan
from renamer.core.model import (
    CapabilityFn,
    FileResult,
    Issue,
    Level,
    Status,
)
from renamer.core.ports import FileSystem, is_case_only_change

from .builder import assemble_pipeline
from .context import Context

__all__ = ["run_file"]


def run_file(
    plan: Plan,
    source: Path,
    calls: Mapping[str, CapabilityFn],
    fs: FileSystem,
) -> FileResult:
    """对单个源文件运行默认流水线，返回 FileResult，实际改名由调用方决定"""
    ctx = Context(source=source, parsed={}, fields={}, issues=[])
    assemble_pipeline(plan, calls).run(ctx)
    return _to_result(ctx, source, fs)


def _to_result(ctx: Context, source: Path, fs: FileSystem) -> FileResult:
    """由最终 ctx 推导 Status 并组装 FileResult"""
    issues = list(ctx.issues)
    target = ctx.target  # 完整目标名（含后缀）
    target_path = Path(target) if target else None

    if any(i.code == "template_mismatch" for i in issues):
        return FileResult(
            source=source, target=None, status=Status.SKIPPED, issues=issues
        )

    if any(i.level is Level.ERROR for i in issues):
        return FileResult(
            source=source, target=target_path, status=Status.FAILED, issues=issues
        )

    # 幂等：目标 == 源（含大小写），大小写敏感
    if target is None or target == source.name:
        return FileResult(
            source=source, target=None, status=Status.SKIPPED, issues=issues
        )

    full = source.parent / target
    if not is_case_only_change(source, full) and fs.exists(full):
        issues.append(
            Issue(
                level=Level.ERROR,
                code="conflict",
                message=f"目标已存在，冲突：{target}",
            )
        )
        return FileResult(
            source=source, target=target_path, status=Status.CONFLICT, issues=issues
        )

    return FileResult(
        source=source, target=target_path, status=Status.SUCCESS, issues=issues
    )
