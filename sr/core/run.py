"""编译产物的批处理入口。"""

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from types import MappingProxyType

from sr.core.compile.rule import CompiledRule
from sr.core.contracts.extender import Extender
from sr.core.runtime.context import PipelineContext
from sr.core.runtime.evaluator import Evaluator
from sr.core.runtime.pipeline import Pipeline, assemble_pipeline
from sr.core.runtime.state import FileState


def run_compiled(
    files: tuple[Path, ...],
    rules: tuple[CompiledRule, ...],
    *,
    extenders: Mapping[str, Extender] | None = None,
    max_workers: int = 1,
) -> Mapping[Path, FileState]:
    """在一个文件批次上运行编译后的规则。

    Args:
        files: 待处理文件路径。
        rules: 按声明顺序尝试的 CompiledRule。
        extenders: 能力名到运行实例的映射。
        max_workers: 分组求值线程数；1 表示单线程。
    Returns:
        路径到最终 FileState 的只读映射。
    Raises:
        ValueError: max_workers 不是正整数。
        PipelineError: 管线前置条件不满足，整个批次中断。
    """
    if type(max_workers) is not int or max_workers < 1:
        raise ValueError("max_workers 必须是正整数")
    pipeline = assemble_pipeline()
    context = PipelineContext(
        files={path: FileState() for path in files},
        rules=rules,
        extenders=extenders if extenders is not None else {},
    )
    if max_workers == 1:
        pipeline.run(context)
    else:
        # 匹配、分组、绑定依赖全批次，完成后才能按组并行。
        Pipeline(pipeline.stages[:3]).run(context)
        _run_groups(context, Pipeline(pipeline.stages[3:]), max_workers)
    return MappingProxyType(dict(context.files))


def _run_groups(context: PipelineContext, pipeline: Pipeline, max_workers: int) -> None:
    """按规则实例和组成员拆分批次并并行执行剩余阶段。"""
    evaluator = context.require_evaluator()
    groups: dict[tuple[int, tuple[Path, ...]], dict[Path, FileState]] = {}
    for path, file in evaluator.sources.items():
        # CompiledRule 不可哈希，用 id 区分规则实例。
        groups.setdefault((id(file.rule), file.group), {})[path] = file

    def evaluate(sources: dict[Path, FileState]) -> dict[Path, FileState]:
        """用独立上下文执行剩余阶段。"""
        # 组内求值只需要本组成员的生产者索引。
        local = PipelineContext(
            files=dict(sources),
            rules=context.rules,
            extenders=context.extenders,
            evaluator=Evaluator(
                sources,
                extenders=context.extenders,
                producers={path: evaluator.producers[path] for path in sources},
            ),
        )
        pipeline.run(local)
        return local.files

    # 每组独立执行剩余阶段，最后由主线程合并结果。
    pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="sr-group")
    try:
        futures = [pool.submit(evaluate, sources) for sources in groups.values()]
        for future in as_completed(futures):
            context.files.update(future.result())
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
