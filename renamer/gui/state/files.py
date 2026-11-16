"""文件树的节点状态，由树交互和批量结果共同更新"""

from dataclasses import dataclass, field
from pathlib import Path

from renamer.app import Status


@dataclass
class TreeNode:
    """按对象身份区分节点，预览目标名与实际路径分别持有"""

    name: str
    path: Path | None = None
    is_dir: bool = False
    children: list["TreeNode"] = field(default_factory=list)
    status: Status | None = None
    checked: bool = False
    open: bool = False
    rename: str | None = None

    def __eq__(self, other: object) -> bool:
        return self is other

    __hash__ = object.__hash__
