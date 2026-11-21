"""顺序执行的管线与阶段契约。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from sr.core.runtime.context import PipelineContext


class PipelineStage(ABC):
    """管线阶段契约。"""

    @abstractmethod
    def process(self, context: PipelineContext) -> None:
        """处理当前批次。

        Args:
            context: 正在运行的 PipelineContext，阶段应原地更新它。
        Raises:
            PipelineError: 前置阶段未完成或批次状态不合法。
        """
        ...


@dataclass(frozen=True)
class Pipeline:
    """按顺序运行阶段并维护待处理集合。"""

    stages: tuple[PipelineStage, ...]

    def run(self, context: PipelineContext) -> None:
        """依次运行全部阶段。

        Args:
            context: 待执行的批次上下文；开始时重建 pending，阶段结束后移除失败成员。
        Raises:
            PipelineError: 阶段前置条件不满足；已更新的状态保留，不回滚。
        """
        context.pending = {
            path: None for path, file in context.files.items() if file.error is None
        }
        context.failed.clear()
        for stage in self.stages:
            try:
                stage.process(context)
            finally:
                for path in context.failed:
                    context.pending.pop(path, None)
                context.failed.clear()


def assemble_pipeline() -> Pipeline:
    """按固定顺序组装标准管线。"""
    # 延迟导入阶段，避免 stages 包与 pipeline 的循环导入。
    from sr.core.runtime.stages import (
        BindingStage,
        ComposingStage,
        ExtendingStage,
        GroupingStage,
        MatchingStage,
        SelectingStage,
    )

    return Pipeline(
        stages=(
            MatchingStage(),
            GroupingStage(),
            BindingStage(),
            SelectingStage(),
            ExtendingStage(),
            ComposingStage(),
        ),
    )
