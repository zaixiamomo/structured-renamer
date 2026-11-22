"""应用层依赖的端口契约。"""

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol

from sr.app.models import FileStamp, Ledger
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

    def scan(self, directory: Path, excluded: tuple[Path, ...]) -> tuple[Path, ...]:
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
    """全局账本存储；load/save 的调用方必须持锁。"""

    def validate_target(self, directory: Path) -> None:
        """拒绝状态目录落入改名扫描范围。

        Args:
            directory: 待改名的扫描根目录。
        Raises:
            ApplicationError: 状态目录位于扫描根目录内。
        """
        ...

    def lock(self) -> AbstractContextManager[None]:
        """获取覆盖账本读取、文件移动和提交的全局进程锁。

        Returns:
            退出时释放锁的上下文管理器。
        Raises:
            ApplicationError: 其他进程正在使用状态。
            OSError: 无法访问锁文件。
        """
        ...

    def load(self) -> Ledger:
        """持锁读取全局账本。

        Returns:
            当前账本；无记录时返回空账本。
        Raises:
            ApplicationError: 状态损坏或格式不兼容。
            OSError: 无法读取状态文件。
        """
        ...

    def save(self, ledger: Ledger) -> None:
        """持锁原子保存全局账本。

        Args:
            ledger: 待提交的完整账本快照。
        Raises:
            OSError: 保存失败；调用方须持锁重读以确认提交结果。
        """
        ...
