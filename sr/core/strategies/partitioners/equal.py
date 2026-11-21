"""等值划分器。"""

from collections.abc import Hashable, Mapping
from typing import TypeVar

from sr.core.contracts.strategies import Partitioner

K = TypeVar("K", bound=Hashable)


class Equal(Partitioner[object]):
    """按值相等划分成组。"""

    name = "equal"

    def split(self, values: Mapping[K, object]) -> tuple[tuple[K, ...], ...]:
        """按与组首成员值相等归组。"""
        groups: list[list[K]] = []
        for member, value in values.items():
            for group in groups:
                if value == values[group[0]]:
                    group.append(member)
                    break
            else:
                groups.append([member])
        return tuple(tuple(group) for group in groups)
