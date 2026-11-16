"""可组合的阶段管线及默认单文件执行入口"""

from __future__ import annotations

from .builder import assemble_pipeline
from .context import Context
from .engine import run_file
from .pipeline import Pipeline
from .stage import Stage

__all__ = ["Context", "Pipeline", "Stage", "assemble_pipeline", "run_file"]
