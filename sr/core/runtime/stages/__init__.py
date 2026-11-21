"""标准管线的各个阶段。"""

from sr.core.runtime.stages.binding import BindingStage
from sr.core.runtime.stages.composing import ComposingStage
from sr.core.runtime.stages.extending import ExtendingStage
from sr.core.runtime.stages.grouping import GroupingStage
from sr.core.runtime.stages.matching import MatchingStage
from sr.core.runtime.stages.selecting import SelectingStage

__all__ = [
    "BindingStage",
    "ComposingStage",
    "ExtendingStage",
    "GroupingStage",
    "MatchingStage",
    "SelectingStage",
]
