"""并集划分组合器。"""

from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from typing import TypeVar

from sr.core.contracts.strategies import Partitioner

K = TypeVar("K", bound=Hashable)


@dataclass(frozen=True)
class Any(Partitioner[object]):
    """任意子划分器连通的成员合并为一组。"""

    name = "any"
    partitioners: tuple[Partitioner, ...]

    def __post_init__(self) -> None:
        """要求至少有一个子划分器。"""
        if not self.partitioners:
            raise ValueError("any 至少需要一个子划分器")

    def split(self, values: Mapping[K, object]) -> tuple[tuple[K, ...], ...]:
        """用并查集合并子划分产生的连通分量。"""
        parents = {key: key for key in values}

        def find(key: K) -> K:
            """查找并压缩并查集根节点。"""
            # 路径减半，避免重复链式查找。
            while parents[key] != key:
                parents[key] = parents[parents[key]]
                key = parents[key]
            return key

        for partitioner in self.partitioners:
            for group in partitioner.split(values):
                root = find(group[0])
                for key in group[1:]:
                    parents[find(key)] = root

        groups: dict[K, list[K]] = {}
        for key in values:
            groups.setdefault(find(key), []).append(key)
        return tuple(tuple(group) for group in groups.values())
