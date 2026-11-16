"""流水线装配：Plan 与能力实现注册表装配为默认阶段 Pipeline"""

from __future__ import annotations

from collections.abc import Mapping

from renamer.core.compile import Plan
from renamer.core.model import CapabilityFn

from .pipeline import Pipeline
from .stages import (
    EnrichStage,
    ParseStage,
    RenderStage,
    SanitizeStage,
    SeedStage,
    ValidateStage,
)

__all__ = ["assemble_pipeline"]


def assemble_pipeline(plan: Plan, calls: Mapping[str, CapabilityFn]) -> Pipeline:
    """把 Plan 与能力实现注册表装配为默认阶段 Pipeline

    Args:
        plan: compile_rule 编译出的静态计划
        calls: cap id 到能力实现函数

    Returns:
        默认阶段 Pipeline（parse/seed/enrich/render/sanitize/validate）
    """
    stages = [
        ParseStage(plan.parse),
        SeedStage(plan.mapping),
        EnrichStage(plan.wire, calls),
        RenderStage(plan.render, plan.mapping, plan.output_steps),
        SanitizeStage(),
        ValidateStage(plan.mapping.required),
    ]
    return Pipeline(stages)
