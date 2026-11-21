"""清洗、转换、分类和划分策略契约。"""

import re
from abc import ABC, abstractmethod
from collections.abc import Hashable, Mapping
from typing import ClassVar, Generic, TypeVar

T = TypeVar("T")
K = TypeVar("K", bound=Hashable)


class Cleaner(ABC):
    """文本清洗步骤。"""

    name: ClassVar[str]

    def clean(self, text: str) -> str:
        """清洗文本。

        Args:
            text: 输入字符串。
        Returns:
            清洗后的字符串。
        Raises:
            TypeError: 输入或子类输出不是 str。
        """
        # 用精确类型检查，避免 str 子类绕过清洗契约。
        if type(text) is not str:
            raise TypeError("清洗输入必须是 str")
        result = self._clean(text)
        if type(result) is not str:
            raise TypeError("清洗输出必须是 str")
        return result

    @abstractmethod
    def _clean(self, text: str) -> str:
        """执行具体清洗并返回 str。"""
        ...


class Converter(ABC, Generic[T]):
    """可逆的文本与值转换。"""

    name: ClassVar[str]

    @abstractmethod
    def forward(self, text: str) -> T:
        """把文本转换为值。

        Args:
            text: 待转换的文本。
        Returns:
            供划分器比较的值，类型由实现决定。
        Raises:
            TypeError: 输入不是 str。
            ValueError: 文本不能转换为目标类型。
        """
        ...

    @abstractmethod
    def backward(self, value: T) -> str:
        """把值还原为文本。

        Args:
            value: forward 返回的值。
        Returns:
            规范化文本，不保证保留原格式。
        Raises:
            TypeError: 值类型不符合契约。
        """
        ...


class Classifier(ABC):
    """单字符类别匹配器。"""

    name: ClassVar[str]
    ranges: ClassVar[str]  # 可直接嵌入正则字符类的范围文本。

    def matches(self, char: str) -> bool:
        """判断字符是否属于 ranges 定义的类别。"""
        return re.fullmatch(f"[{self.ranges}]", char) is not None


class Partitioner(ABC, Generic[T]):
    """把同组值划分成若干成员集合。"""

    name: ClassVar[str]

    @abstractmethod
    def split(self, values: Mapping[K, T]) -> tuple[tuple[K, ...], ...]:
        """划分值映射。

        Args:
            values: 待划分的键到值映射。
        Returns:
            若干组键元组；同组内的键满足该划分器的关系。
        """
        ...
