"""按需执行拓展并汇总组内来源共识。"""

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from sr.core.compile.extension import CompiledExtension
from sr.core.contracts.extender import Extender
from sr.core.errors import PipelineError
from sr.core.runtime.state import FileState
from sr.core.system import read_system_values
from sr.core.values import TokenValue

NodeKey = tuple[Path, CompiledExtension]


class BorrowError(ValueError):
    """组内借用来源求值失败。"""

    def __init__(self, name: str, failures: dict[Path, Exception]) -> None:
        """保存失败字段与各来源的异常。"""
        self.failures = MappingProxyType(dict(failures))
        super().__init__(
            f"借用字段 {name!r} 失败："
            + "; ".join(f"{path}: {error}" for path, error in failures.items())
        )


class Evaluator:
    """按需求值 CompiledExtension，并复用组内同名字段的共识值。"""

    def __init__(
        self,
        files: Mapping[Path, FileState],
        *,
        extenders: Mapping[str, Extender],
        producers: Mapping[Path, Mapping[str, tuple[CompiledExtension, ...]]],
    ) -> None:
        """建立批次或组内的求值缓存。

        Args:
            files: 绑定阶段的 FileState 快照；后续阶段更新不会回写这里。
            extenders: 能力名到实例的映射。
            producers: 各文件可用的输出词段到 CompiledExtension 候选的映射。
        """
        self.sources = MappingProxyType(dict(files))
        self._extenders = MappingProxyType(dict(extenders))
        self.producers = MappingProxyType(
            {
                path: MappingProxyType(
                    {name: tuple(nodes) for name, nodes in member.items()}
                )
                for path, member in producers.items()
            }
        )
        self._results: dict[
            Path, dict[CompiledExtension, Mapping[str, TokenValue] | Exception]
        ] = {path: {} for path in self.sources}
        self._reachable: dict[tuple[Path, str], bool] = {}
        self._sources: dict[tuple[int, tuple[Path, ...], str], tuple[Path, ...]] = {}
        self._consensus: dict[tuple[tuple[Path, ...], str], TokenValue] = {}

    def _source(self, path: Path) -> FileState:
        """读取绑定时的 FileState，未知成员抛 PipelineError。"""
        try:
            return self.sources[path]
        except KeyError as exc:
            raise PipelineError("文件尚未完成来源绑定") from exc

    def _local_source(self, path: Path, name: str) -> bool:
        """根据捕获或生产者声明判断本地来源，不执行求值。"""
        source = self._source(path)
        return name in source.captures or bool(self.producers[path].get(name))

    def _borrow_sources(self, path: Path, name: str) -> tuple[Path, ...]:
        """按同一 CompiledRule 和 group 查找真实来源，排除当前成员。"""
        source = self._source(path)
        # CompiledRule 含不可哈希字段，用 id 区分规则实例。
        key = (id(source.rule), source.group, name)
        if key not in self._sources:
            self._sources[key] = tuple(
                member
                for member in dict.fromkeys(source.group)
                if member in self.sources
                and self.sources[member].rule is source.rule
                and self._local_source(member, name)
            )

        return tuple(member for member in self._sources[key] if member != path)

    def has_source(self, path: Path, name: str) -> bool:
        """判断字段是否具有本地或组内来源。

        Args:
            path: 批次的成员路径。
            name: 待检查的字段名。
        Returns:
            存在捕获值、生产者或可借用的组内来源时为 True。
        """
        return self._local_source(path, name) or bool(self._borrow_sources(path, name))

    def can_produce(self, path: Path, name: str) -> bool:
        """判断字段是否可完整生产。

        Args:
            path: 批次的成员路径。
            name: 待检查的字段名。
        Returns:
            依赖链闭合且无循环时为 True；结果按文件与字段缓存。
        Raises:
            PipelineError: path 不属于已绑定成员。
            NotImplementedError: 同一字段存在多个生产者。
        """
        key = (path, name)
        if key not in self._reachable:
            self._reachable[key] = self._can_produce_token(path, name, active=set())
        return self._reachable[key]

    def _can_produce_token(self, path: Path, name: str, active: set[NodeKey]) -> bool:
        """递归检查字段的生产者输入是否都能生产。"""
        source = self._source(path)
        if name in source.captures:
            return True
        producers = self.producers[path].get(name, ())
        if not producers:
            sources = self._borrow_sources(path, name)
            return bool(sources) and all(
                self._can_produce_token(source, name, active) for source in sources
            )
        if len(producers) != 1:
            raise NotImplementedError(f"尚未支持多个生产者：{path} 的 {name!r}")
        node = producers[0]
        key = (path, node)
        # active 是当前依赖链，重复出现即存在循环。
        if key in active:
            return False
        active.add(key)
        try:
            return all(
                self._can_produce_token(path, token.name, active)
                for token in node.inputs.values()
            )
        finally:
            active.remove(key)

    def require(self, path: Path, name: str) -> TokenValue:
        """取得字段值，必要时执行拓展或借用组内来源。

        Args:
            path: 批次的成员路径。
            name: 待求值的字段名。
        Returns:
            本地捕获、生产者输出或组内一致的 TokenValue。
        Raises:
            KeyError: 字段没有任何来源。
            ValueError: 组内值冲突或存在循环依赖。
            BorrowError: 一个或多个借用来源求值失败。
            NotImplementedError: 同一字段存在多个生产者。
            PipelineError: path 不属于已绑定成员。
        """
        return self._require_token(path, name, active=set())

    def _require_token(
        self,
        path: Path,
        name: str,
        active: set[NodeKey],
    ) -> TokenValue:
        """实现 require 的递归求值，并用 active 检测节点循环。"""
        source = self._source(path)
        if name in source.captures:
            return source.captures[name]
        producers = self.producers[path].get(name, ())
        if not producers:
            return self._borrow_token(path, name, active)
        if len(producers) != 1:
            raise NotImplementedError(f"尚未支持多个生产者：{path} 的 {name!r}")
        result = self._require_node(path, producers[0], active)
        return result[name]

    def _borrow_token(self, path: Path, name: str, active: set[NodeKey]) -> TokenValue:
        """在组内其他成员中求值并验证值一致。"""
        sources = self._borrow_sources(path, name)
        if not sources:
            raise KeyError(f"缺少 token：{path} 的 {name!r}")
        key = (sources, name)
        if key in self._consensus:
            return self._consensus[key]
        values: list[TokenValue] = []
        failures: dict[Path, Exception] = {}
        for source in sources:
            try:
                values.append(self._require_token(source, name, active))
            except PipelineError:
                raise
            except Exception as exc:
                failures[source] = exc
        if failures:
            raise BorrowError(name, failures) from next(iter(failures.values()))
        # 只比较计算值；raw 和加工链沿用首个来源。
        first = values[0]
        if any(value.value != first.value for value in values[1:]):
            raise ValueError(f"组内字段 {name!r} 的真实来源值冲突：{sources}")
        self._consensus[key] = first
        return first

    def _require_node(
        self,
        path: Path,
        node: CompiledExtension,
        active: set[NodeKey],
    ) -> Mapping[str, TokenValue]:
        """执行生产者节点并缓存结果或异常。"""
        results = self._results[path]
        cached = results.get(node)
        # 失败结果也缓存，避免重复执行带副作用的拓展。
        if isinstance(cached, Exception):
            raise cached
        if cached is not None:
            return cached
        key = (path, node)
        if key in active:
            outputs = ", ".join(token.name for token in node.outputs.values())
            raise ValueError(f"拓展循环依赖：{path}，输出 {outputs}")
        active.add(key)
        try:
            token_values = {
                token.name: self._require_token(path, token.name, active)
                for token in node.inputs.values()
            }
            result = self._execute_node(path, node, token_values)
        except PipelineError:
            raise
        except Exception as exc:
            results[node] = exc
            raise
        else:
            results[node] = result
            return result
        finally:
            active.remove(key)

    def _execute_node(
        self,
        path: Path,
        node: CompiledExtension,
        token_values: Mapping[str, TokenValue],
    ) -> Mapping[str, TokenValue]:
        """执行单个拓展并检测输出冲突。"""
        # 已完成的拓展输出可以继续供后续节点使用，但同名值必须一致。
        available = dict(self.sources[path].captures)
        for result in self._results[path].values():
            if not isinstance(result, Exception):
                for name, value in result.items():
                    available.setdefault(name, value)
        available.update(token_values)
        extender = self._extenders[node.name]
        system_values = read_system_values(extender.system_bindings, self.sources[path])
        outputs = node.execute(token_values, extender, system_values)
        completed: dict[str, TokenValue] = {}
        for name, value in outputs.items():
            existing = available.get(name)
            if existing is not None:
                if existing.value != value.value:
                    raise ValueError(f"拓展输出 token {name!r} 与已有值冲突")
                completed[name] = existing
            else:
                completed[name] = value
        return MappingProxyType(completed)
