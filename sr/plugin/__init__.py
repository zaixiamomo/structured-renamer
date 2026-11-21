"""插件领域、能力目录和资源接口。"""

from sr.plugin.catalog import Domain, PluginCatalog
from sr.plugin.resources import ExtenderResources

__all__ = [
    "Domain",
    "ExtenderResources",
    "PluginCatalog",
]
