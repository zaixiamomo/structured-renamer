"""文件夹扫描：把用户导入的一个或多个文件夹构建成文件树（TreeNode）"""

from pathlib import Path

from .state.files import TreeNode

__all__ = ["scan_dirs"]


def scan_dirs(paths: list[Path]) -> TreeNode:
    """把多个文件夹扫描成一个合成根（每个文件夹一个子节点）"""
    return TreeNode(name="", is_dir=True, children=[_scan_dir(p) for p in paths])


def _scan_dir(path: Path) -> TreeNode:
    """递归扫描目录构建 TreeNode（目录在前、名称升序），节点带真实 path"""
    children = []
    try:
        entries = sorted(path.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
    except OSError:
        return TreeNode(name=path.name, path=path, is_dir=True)
    for entry in entries:
        children.append(
            _scan_dir(entry)
            if entry.is_dir()
            else TreeNode(name=entry.name, path=entry)
        )
    return TreeNode(name=path.name, path=path, is_dir=True, children=children)
