"""文件行状态映射语义色令牌（tree_view 取 tint，tree_scrollbar 取 mark）"""

from renamer.app import Status

__all__ = ["STATUS_STYLE"]

# Status 映射（行底色, 小地图标记），None 表该维度无视觉标记
STATUS_STYLE: dict[Status, tuple[str | None, str | None]] = {
    Status.SUCCESS: (None, None),
    Status.SKIPPED: ("color.warn.soft", "color.warn"),
    Status.CONFLICT: ("color.err.soft", "color.err"),
    Status.FAILED: ("color.err.soft", "color.err"),
}
