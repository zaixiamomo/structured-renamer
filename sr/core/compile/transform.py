"""加工链表达式 DSL 的编译。"""

import ast
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from sr.core.contracts.compilable import Compilable
from sr.core.contracts.strategies import Cleaner
from sr.core.strategies import CLEANERS


@dataclass(frozen=True)
class CompiledTransform:
    """按顺序执行的清洗器序列。"""

    cleaners: tuple[Cleaner, ...]

    def clean(self, text: str) -> str:
        """依次应用清洗器。

        Args:
            text: 待清洗文本。
        Returns:
            最后一步的结果；空加工链返回原文。
        Raises:
            TypeError: 输入或任一清洗结果不是 str。
        """
        if type(text) is not str:
            raise TypeError("清洗输入必须是 str")
        for cleaner in self.cleaners:
            text = cleaner.clean(text)
        return text


class Transform(BaseModel, Compilable[CompiledTransform]):
    """用 | 连接的清洗器链声明。"""

    text: str

    model_config = ConfigDict(frozen=True, extra="forbid")

    def __init__(self, text: str) -> None:
        """接受用 | 连接的清洗器链。"""
        super().__init__(text=text)

    def compile(self) -> CompiledTransform:
        """解析并实例化清洗器。

        支持用 ``|`` 连接的名称，或仅含常量位置参数的调用。

        Returns:
            已编译的清洗器序列；空文本表示无加工。
        Raises:
            ValueError: 表达式结构或清洗器名称不合法。
            SyntaxError: Python 语法错误。
        """
        cleaners: list[Cleaner] = []
        if not self.text.strip():
            return CompiledTransform(())
        expression = ast.parse(self.text.strip(), mode="eval").body
        pending = [expression]
        while pending:
            part = pending.pop()
            if isinstance(part, ast.BinOp) and isinstance(part.op, ast.BitOr):
                # 先压右再压左，弹出顺序即书写顺序。
                pending.extend((part.right, part.left))
                continue
            if isinstance(part, ast.Name):
                name, arguments = part.id, []
            elif (
                isinstance(part, ast.Call)
                and isinstance(part.func, ast.Name)
                and not part.keywords
                and all(isinstance(arg, ast.Constant) for arg in part.args)
            ):
                name = part.func.id
                arguments = [arg.value for arg in part.args]
            else:
                raise ValueError("加工步骤必须是名称或仅含常量位置参数的调用")
            cleaner_type = CLEANERS.get(name)
            if cleaner_type is None:
                raise ValueError(f"未知加工步骤：{name}")
            cleaners.append(cleaner_type(*arguments))
        return CompiledTransform(tuple(cleaners))
