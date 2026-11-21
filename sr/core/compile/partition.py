"""分组划分表达式 DSL 的编译。"""

import ast
from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ConfigDict

from sr.core.contracts.compilable import Compilable
from sr.core.contracts.strategies import Partitioner
from sr.core.strategies import PARTITIONERS
from sr.core.strategies.partitioners import All, Any

K = TypeVar("K", bound=Hashable)


@dataclass(frozen=True)
class CompiledPartition:
    """已选定的划分器。"""

    partitioner: Partitioner

    def split(self, values: Mapping[K, object]) -> tuple[tuple[K, ...], ...]:
        """委托给划分器执行。"""
        return self.partitioner.split(values)


class Partition(BaseModel, Compilable[CompiledPartition]):
    """any/all/equal/edit_distance 等划分表达式声明。"""

    text: str

    model_config = ConfigDict(frozen=True, extra="forbid")

    def __init__(self, text: str) -> None:
        """接受划分表达式。"""
        super().__init__(text=text)

    def compile(self) -> CompiledPartition:
        """编译划分表达式。

        Returns:
            CompiledPartition；复合划分器会递归编译。
        Raises:
            ValueError: 表达式结构、子划分器或参数不合法。
            SyntaxError: Python 语法错误。
        """
        expression = ast.parse(self.text.strip(), mode="eval").body
        return CompiledPartition(self._compile_partition(expression))

    def _compile_partition(self, expression: ast.expr) -> Partitioner:
        """递归编译名称或调用形式的划分器。"""
        if isinstance(expression, ast.Name):
            name = expression.id
            arguments = ()
        elif (
            isinstance(expression, ast.Call)
            and isinstance(expression.func, ast.Name)
            and not expression.keywords
        ):
            name = expression.func.id
            arguments = expression.args
        else:
            raise ValueError("划分表达式必须是名称或函数调用")
        # any/all 是递归组合子，其余名称从 PARTITIONERS 注册表查找。
        if name in {"any", "all"}:
            if not arguments:
                raise ValueError(f"{name} 至少需要一个子划分器")
            partitioners = tuple(
                self._compile_partition(argument) for argument in arguments
            )
            composite = Any if name == "any" else All
            return composite(partitioners)
        partitioner_type = PARTITIONERS.get(name)
        if partitioner_type is None:
            raise ValueError(f"未知划分器：{name}")
        return partitioner_type(*(self._argument(argument) for argument in arguments))

    @staticmethod
    def _argument(expression: ast.expr) -> object:
        """只接受 Python 字面量参数。"""
        if isinstance(expression, ast.Constant):
            return expression.value
        raise ValueError("划分器参数必须是字面量")
