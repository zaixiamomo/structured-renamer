"""应用层依赖的端口契约。"""

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol

from sr.app.models import DirectoryState, FileStamp
from sr.core.compile.rule import Rule


class RuleCodec(Protocol):
    """Rule 文本编解码契约。"""

    def decode(self, text: str) -> Rule:
        """解析规则文本；底层解析异常原样传播。

        Args:
            text: 完整的规则文档文本。
        Returns:
            校验后的 Rule，尚未编译。
        Raises:
            TypeError: text 不是字符串。
            ValueError: 规则语法或结构非法。
        """
        ...

    def encode(self, value: Rule) -> str:
        """序列化规则。

        Args:
            value: 待编码的规则。
        Returns:
            可再次 decode 的文本，不保证保留原格式。
        Raises:
            TypeError: value 不是 Rule。
        """
        ...


class FileSystem(Protocol):
    """重命名所需的本地文件系统契约。"""

    def resolve(self, directory: Path) -> Path:
        """校验并解析目录路径。

        Args:
            directory: 必须是普通目录。
        Returns:
            解析后的绝对路径。
        Raises:
            ValueError: 路径不是普通目录。
            OSError: 无法解析路径或文件系统未提供可靠身份。
        """
        ...

    def read(self, path: Path) -> str:
        """读取 UTF-8 文本文件。

        Args:
            path: 待读取文件，允许以 BOM 开头。
        Returns:
            不含 BOM 的文本。
        Raises:
            OSError: 文件无法读取。
        """
        ...

    def scan(
        self, directory: Path, excluded: tuple[Path, ...]
    ) -> tuple[Path, ...]:
        """递归收集普通文件。

        Args:
            directory: 扫描起始目录，必须是普通目录。
            excluded: 要排除的文件路径，按 key 判等。
        Returns:
            按路径排序的文件元组；跳过链接、重解析点和 excluded 成员。
        Raises:
            ValueError: 路径不是普通目录。
            OSError: 目录无法读取。
        """
        ...

    def stat(self, path: Path) -> FileStamp:
        """读取文件身份快照。

        Args:
            path: 普通文件路径。
        Returns:
            FileStamp，含文件与父目录身份、大小和修改时间。
        Raises:
            ValueError: 文件或父目录类型不符。
            OSError: 无法读取状态或文件系统未提供可靠身份。
        """
        ...

    def key(self, path: Path) -> tuple[int, int, str]:
        """生成文件名称位置的比较键。

        Args:
            path: 文件路径；父目录须存在，文件本身可以不存在。
        Returns:
            父目录标识与按目录大小写规则处理的文件名。
        Raises:
            ValueError: 父目录不是普通目录。
            OSError: 文件系统未提供可靠身份。
        """
        ...

    def exists(self, path: Path) -> bool:
        """判断路径是否已被占用。

        Args:
            path: 待检查的路径。
        Returns:
            被占用时为 True，悬空链接也算占用。
        """
        ...

    def rename(self, source: Path, target: Path) -> None:
        """同目录内原子改名，不覆盖已有目标。

        Args:
            source: 当前文件路径。
            target: 同目录内未被占用的目标路径。
        Raises:
            ValueError: source 与 target 不在同一目录。
            FileExistsError: 目标已存在。
            OSError: 平台不支持或底层改名失败。
        """
        ...


class StateStore(Protocol):
    """目录状态持久化契约。"""

    def lock(self, directory: Path) -> AbstractContextManager[None]:
        """获取状态存储的互斥访问权。

        Args:
            directory: 本次操作目录；状态存储须位于其外部。
        Yields:
            None；读取、文件操作和写回应在同一上下文内完成。
        Raises:
            ApplicationError: 锁冲突、状态存储位置无效，或重叠目录存在未完成操作。
        """
        ...

    def load(self, directory: Path) -> DirectoryState:
        """读取目录状态。

        Args:
            directory: 待读取状态的目录；调用方须已持锁。
        Returns:
            DirectoryState；无记录时为空状态。
        Raises:
            ApplicationError: 状态记录损坏或版本不兼容。
        """
        ...

    def save(self, state: DirectoryState) -> None:
        """校验并原子替换目录状态。

        Args:
            state: 完整的 DirectoryState，含撤销记录和未完成操作；调用方须已持锁。
                不保存 RenamePlan 或 ExecutionReport。
        Raises:
            OSError: 写入或替换失败，原状态文件保持不变。
        """
        ...
