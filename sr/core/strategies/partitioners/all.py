"""交集划分组合器。"""

from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from typing import TypeVar

from sr.core.contracts.strategies import Partitioner

K = TypeVar("K", bound=Hashable)


@dataclass(frozen=True)
class All(Partitioner[object]):
    """要求所有子划分器都把成员划为同组的组合器。"""

    name = "all"
    partitioners: tuple[Partitioner, ...]

    def __post_init__(self) -> None:
        """要求至少有一个子划分器。"""
        if not self.partitioners:
            raise ValueError("all 至少需要一个子划分器")

    def split(self, values: Mapping[K, object]) -> tuple[tuple[K, ...], ...]:
        """按各子划分的组号组合签名合并。"""
        memberships = [
            {
                key: index
                for index, group in enumerate(partitioner.split(values))
                for key in group
            }
            for partitioner in self.partitioners
        ]
        groups: dict[tuple[int, ...], list[K]] = {}
        for key in values:
            signature = tuple(membership[key] for membership in memberships)
            groups.setdefault(signature, []).append(key)
        return tuple(tuple(group) for group in groups.values())
