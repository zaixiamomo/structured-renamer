"""内置策略注册表。"""

from types import MappingProxyType

from .classifiers import Chinese, Digits, English
from .cleaners import Capitalize, DateFormat, Lower, Replace, Trim, Upper, Zpad
from .converters import Integer
from .partitioners import EditDistance, Equal

# 注册表只暴露名称到实现类的映射，实例化由编译层负责。
CLASSIFIERS = MappingProxyType({item.name: item for item in (Digits, English, Chinese)})
CLEANERS = MappingProxyType(
    {
        item.name: item
        for item in (Lower, Upper, Trim, Capitalize, Replace, Zpad, DateFormat)
    }
)
CONVERTERS = MappingProxyType({Integer.name: Integer})
PARTITIONERS = MappingProxyType({item.name: item for item in (Equal, EditDistance)})

__all__ = ["CLASSIFIERS", "CLEANERS", "CONVERTERS", "PARTITIONERS"]
