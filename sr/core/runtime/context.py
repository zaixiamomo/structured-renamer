"""管线批次的共享上下文。"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from sr.core.contracts.extender import Extender
from sr.core.errors import FileError, PipelineError
from sr.core.runtime.state import FileState

if TYPE_CHECKING:
    from sr.core.compile.rule import CompiledRule
    from sr.core.runtime.evaluator import Evaluator


@dataclass
class PipelineContext:
    """一次管线运行的批次状态。"""

    files: dict[Path, FileState]
    rules: tuple[CompiledRule, ...]
    evaluator: Evaluator | None = None
    pending: dict[Path, None] = field(default_factory=dict)
    failed: set[Path] = field(default_factory=set)
    extenders: Mapping[str, Extender] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """冻结拓展映射并为状态补全路径。"""
        self.extenders = MappingProxyType(dict(self.extenders))
        self.files = {
            path: replace(file, path=path) if file.path is None else file
            for path, file in self.files.items()
        }

    def fail(self, path: Path, error: FileError) -> None:
        """记录成员失败。

        Args:
            path: 当前批次内的成员。
            error: 归属该成员的 FileError。
        Raises:
            PipelineError: path 不属于批次或错误类型不符。
        """
        if path not in self.files:
            raise PipelineError("文件不属于当前批次")
        if not isinstance(error, FileError):
            raise PipelineError("文件失败必须使用 FileError")
        # 只保留第一个失败，后续阶段不覆盖根因。
        if self.files[path].error is None:
            self.files[path] = replace(self.files[path], error=error)
        self.failed.add(path)

    @contextmanager
    def file_scope(self, stage: str, *paths: Path) -> Iterator[None]:
        """把成员执行包裹在文件级错误边界内。

        阶段前置条件应在此上下文之外检查；已有 FileError 保留原对象和异常链。

        Args:
            stage: 用于构造 FileError 的阶段名。
            *paths: 受影响的成员，必须都属于当前批次。
        Yields:
            执行调用方逻辑；普通异常会转为 FileError 并标记失败。
        Raises:
            PipelineError: 参数无效或管线契约错误。
        """
        if not paths or any(path not in self.files for path in paths):
            raise PipelineError("文件错误边界必须指定当前批次的成员")
        try:
            yield
        except PipelineError:
            # 管线契约错误不可归因到单个文件，直接上抛。
            raise
        except Exception as exc:
            error = exc if isinstance(exc, FileError) else FileError(stage, exc)
            for path in paths:
                self.fail(path, error)

    def require_evaluator(self) -> Evaluator:
        """取得已完成绑定的 Evaluator。

        Raises:
            PipelineError: BindingStage 尚未运行。
        """
        if self.evaluator is None:
            raise PipelineError("尚未完成来源绑定，请先执行 BindingStage")
        return self.evaluator
