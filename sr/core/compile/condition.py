"""parse/render 条件表达式 DSL 的编译。"""

from __future__ import annotations

import ast
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from sr.core.contracts.compilable import Compilable
from sr.core.system import SystemField

if TYPE_CHECKING:
    from sr.core.runtime.state import FileState

Fields = Mapping[str, str]
Predicate = Callable[[Fields, "FileState | None"], bool]
ValueReader = Callable[[Fields, "FileState | None"], str | tuple[str, ...]]


@dataclass(frozen=True)
class CompiledCondition:
    """已编译的布尔条件。"""

    predicate: Predicate

    def evaluate(self, fields: Fields, *, file: FileState | None = None) -> bool:
        """在字段和文件上下文上求值。

        Args:
            fields: 字段名到文本值的映射，按表达式短路规则读取。
            file: 读取系统字段所需的 FileState；无系统字段引用时可省略。
        Returns:
            条件是否成立。
        """
        return self.predicate(fields, file)


class Condition(BaseModel, Compilable[CompiledCondition]):
    """单行 Python 表达式子集构成的条件声明。"""

    text: str

    model_config = ConfigDict(frozen=True, extra="forbid")

    def __init__(self, text: str) -> None:
        """接受单行条件表达式。"""
        super().__init__(text=text)

    def compile(self) -> CompiledCondition:
        """把条件文本编译为谓词。

        Returns:
            CompiledCondition；调用时才对字段求值。
        Raises:
            ValueError: 表达式为空、多行或包含不支持的语法。
            SyntaxError: Python 语法错误。
        """
        if not self.text.strip() or len(self.text.splitlines()) != 1:
            raise ValueError("条件必须是非空单行表达式")

        tree = ast.parse(self.text.strip(), mode="eval")
        return CompiledCondition(
            predicate=self._compile_condition(tree.body),
        )

    def _compile_condition(self, node: ast.expr) -> Predicate:
        """递归编译布尔、比较和 exists 表达式。"""
        if isinstance(node, ast.BoolOp):
            predicates = tuple(self._compile_condition(value) for value in node.values)

            if isinstance(node.op, ast.And):
                return lambda fields, file: all(
                    predicate(fields, file) for predicate in predicates
                )

            if isinstance(node.op, ast.Or):
                return lambda fields, file: any(
                    predicate(fields, file) for predicate in predicates
                )

        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            predicate = self._compile_condition(node.operand)
            return lambda fields, file: not predicate(fields, file)

        if isinstance(node, ast.Compare):
            return self._compile_compare(node)

        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "exists"
            and len(node.args) == 1
            and not node.keywords
        ):
            reference = self._reference(node.args[0])
            if isinstance(reference, SystemField):
                return lambda fields, file: reference.read(file) is not None
            return lambda fields, file: reference in fields

        raise ValueError("不支持的条件表达式")

    def _compile_compare(self, node: ast.Compare) -> Predicate:
        """编译单次 Eq/NotEq/In/NotIn 比较。"""
        if len(node.ops) != 1:
            raise ValueError("不支持连续比较")

        left = self._compile_value(node.left)
        right = self._compile_value(node.comparators[0])
        operator = node.ops[0]

        if isinstance(operator, ast.Eq):
            return lambda fields, file: left(fields, file) == right(fields, file)

        if isinstance(operator, ast.NotEq):
            return lambda fields, file: left(fields, file) != right(fields, file)

        if isinstance(operator, ast.In):
            return lambda fields, file: left(fields, file) in right(fields, file)

        if isinstance(operator, ast.NotIn):
            return lambda fields, file: left(fields, file) not in right(fields, file)

        raise ValueError("不支持的比较运算")

    def _compile_value(self, node: ast.expr) -> ValueReader:
        """编译字段引用、字符串字面量或字符串列表。"""
        if isinstance(node, (ast.Name, ast.Attribute)):
            reference = self._reference(node)
            if isinstance(reference, SystemField):
                # 系统字段统一转 str，便于与字符串条件比较。
                return lambda fields, file: str(reference.read(file))
            return lambda fields, file: fields[reference]

        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            return lambda fields, file: value

        if isinstance(node, ast.List):
            if not all(
                isinstance(item, ast.Constant) and isinstance(item.value, str)
                for item in node.elts
            ):
                raise ValueError("候选列表只能包含字符串")

            values = tuple(item.value for item in node.elts)
            return lambda fields, file: values

        raise ValueError("只支持字段、字符串和字符串列表")

    def _reference(self, node: ast.expr) -> str | SystemField:
        """把 Name 或 file.attr 解析为字段名或 SystemField。"""
        if isinstance(node, ast.Name):
            return node.id
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "file"
        ):
            # 只放行已在 SystemField 中声明的 file.* 属性。
            try:
                return SystemField(f"file.{node.attr}")
            except ValueError as exc:
                raise ValueError("未知文件属性") from exc
        raise ValueError("只支持词段名称和已声明的 file.* 文件属性")
