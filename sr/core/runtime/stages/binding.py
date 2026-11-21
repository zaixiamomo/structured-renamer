"""校验匹配与分组结果并建立求值器。"""

from types import MappingProxyType

from sr.core.contracts.extender import Extender
from sr.core.errors import PipelineError
from sr.core.runtime.context import PipelineContext
from sr.core.runtime.evaluator import Evaluator
from sr.core.runtime.pipeline import PipelineStage
from sr.core.system import check_system_bindings, read_system_values


class BindingStage(PipelineStage):
    """校验批次并创建 Evaluator。"""

    def process(self, context: PipelineContext) -> None:
        """为本批次建立来源绑定和能力实例。"""
        if context.evaluator is not None:
            raise PipelineError("本批次已完成来源绑定")
        sources = {}
        for path, file in context.files.items():
            # 已有错误的成员跳过绑定，但仍保留在 files 中。
            if file.rule is None:
                if file.error is None:
                    raise PipelineError("尚未完成匹配，请先执行 MatchingStage")
                continue
            if not file.group:
                raise PipelineError("尚未完成分组，请先执行 GroupingStage")
            for name in (*file.captures, *file.rule.producers):
                if not name.isidentifier():
                    raise PipelineError("捕获和生产目标必须是普通词段")
            sources[path] = file

        nodes = dict.fromkeys(
            node
            for source in sources.values()
            for producers in source.rule.producers.values()
            for node in producers
        )
        extenders = context.extenders
        for node in nodes:
            instance = extenders.get(node.name)
            if instance is None:
                raise PipelineError(f"缺少拓展运行实例：{node.name}")
            if not isinstance(instance, Extender):
                raise PipelineError(f"拓展绑定必须是 Extender：{node.name}")
            if (
                not isinstance(instance.input_ports, tuple)
                or not isinstance(instance.output_ports, tuple)
                or len(instance.input_ports) != len(node.inputs)
                or set(instance.input_ports) != set(node.inputs)
                or not set(node.outputs) <= set(instance.output_ports)
            ):
                raise PipelineError(f"拓展运行实例端口不匹配：{node.name}")
            check_system_bindings(instance.system_bindings)
            if any(
                not token.name.isidentifier()
                for token in (*node.inputs.values(), *node.outputs.values())
            ):
                raise PipelineError("拓展输入输出必须使用普通词段")

        producers = {}
        for path, file in sources.items():
            # 逐个能力读取系统字段并调用 supports()，只保留适用的生产者。
            applicable = {}
            names = dict.fromkeys(
                node.name
                for candidates in file.rule.producers.values()
                for node in candidates
            )
            for name in names:
                instance = extenders[name]
                try:
                    system_values = read_system_values(instance.system_bindings, file)
                    supported = instance.supports(system_values)
                    if type(supported) is not bool:
                        raise TypeError("Extender.supports 必须返回 bool")
                    applicable[name] = supported
                except PipelineError:
                    raise
                except Exception as exc:
                    raise PipelineError(
                        f"拓展适用范围判断失败：{path} 的 {name}"
                    ) from exc
            producers[path] = MappingProxyType(
                {
                    name: active
                    for name, candidates in file.rule.producers.items()
                    if (
                        active := tuple(
                            node for node in candidates if applicable[node.name]
                        )
                    )
                }
            )

        context.evaluator = Evaluator(sources, extenders=extenders, producers=producers)
