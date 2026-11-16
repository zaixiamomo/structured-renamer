"""具体领域插件聚合：anime + _builtin，供组合根显式装配"""

from __future__ import annotations

from renamer.core.plugins import DomainRegistry

from . import _builtin, anime

__all__ = ["_builtin", "anime", "default_registry"]


def default_registry() -> DomainRegistry:
    """默认领域注册表（_builtin 在前、anime 在后，注册序即展示序/覆盖序）"""
    return DomainRegistry((_builtin.domain, anime.domain))
