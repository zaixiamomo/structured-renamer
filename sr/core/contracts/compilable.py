"""声明对象到编译产物的通用契约。"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T_co = TypeVar("T_co", covariant=True)


class Compilable(ABC, Generic[T_co]):
    """可编译为运行期产物的声明对象。"""

    @abstractmethod
    def compile(self, *args: object, **kwargs: object) -> T_co:
        """编译为运行期对象。

        Args:
            *args: 由声明类型定义的编译参数。
            **kwargs: 由声明类型定义的编译选项。
        Returns:
            可直接执行的编译产物。
        """
        ...
