"""编辑距离划分器。"""

from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from typing import TypeVar

from sr.core.contracts.strategies import Partitioner

K = TypeVar("K", bound=Hashable)


@dataclass(frozen=True)
class EditDistance(Partitioner[str]):
    """按最大编辑距离贪心聚类的划分器。"""

    name = "edit_distance"
    max_distance: int

    def __post_init__(self) -> None:
        """校验阈值。

        Raises:
            TypeError: max_distance 不是 int。
            ValueError: max_distance 为负。
        """
        if type(self.max_distance) is not int:
            raise TypeError("编辑距离阈值必须是 int")
        if self.max_distance < 0:
            raise ValueError("编辑距离阈值不能为负数")

    def split(self, values: Mapping[K, str]) -> tuple[tuple[K, ...], ...]:
        """按输入顺序贪心成组。"""
        if any(type(value) is not str for value in values.values()):
            raise TypeError("编辑距离输入必须是 str")
        groups: list[list[K]] = []
        for member, value in values.items():
            # 与已成立组内所有成员都足够接近才加入，避免链式传递扩大组。
            for group in groups:
                if all(self._within_distance(value, values[peer]) for peer in group):
                    group.append(member)
                    break
            else:
                groups.append([member])
        return tuple(tuple(group) for group in groups)

    def _within_distance(self, left: str, right: str) -> bool:
        """用滚动一行动态规划判断距离是否不超过阈值。"""
        if abs(len(left) - len(right)) > self.max_distance:
            return False
        if left == right:
            return True
        if len(left) < len(right):
            left, right = right, left
        previous = list(range(len(right) + 1))
        for row, left_char in enumerate(left, start=1):
            current = [row]
            for column, right_char in enumerate(right, start=1):
                current.append(
                    min(
                        previous[column] + 1,
                        current[column - 1] + 1,
                        previous[column - 1] + (left_char != right_char),
                    )
                )
            previous = current
        return previous[-1] <= self.max_distance
