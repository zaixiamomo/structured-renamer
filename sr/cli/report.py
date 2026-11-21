"""把计划和执行结果格式化为终端文本。"""

import unicodedata

from sr.app.models import ExecutionReport, RenamePlan


def _display_width(text: str) -> int:
    """按终端显示宽度计算文本列数。"""
    # 全角/宽字符占两列，组合标记和格式字符不占列。
    return sum(
        2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
        for char in text
        if unicodedata.category(char) not in ("Mn", "Me", "Cf")
    )


def _format_move(source: str, target: str, width: int) -> str:
    """对齐源名称后追加箭头和目标名。"""
    padding = " " * (width - _display_width(source))
    return f"{source}{padding} -> {target}"


def format_plan(plan: RenamePlan, *, errors_only: bool = False) -> str:
    """渲染改名计划。

    Args:
        plan: 待显示计划。
        errors_only: 为 True 时只输出错误项。
    Returns:
        每行一个成员的多行文本；无内容时返回空串。
    Raises:
        ValueError: 需要展示的成员缺少 target。
    """
    width = max(
        (_display_width(item.source.name) for item in plan.items if item.error is None),
        default=0,
    )
    lines = []
    for item in plan.items:
        if item.error is not None:
            lines.append(f"[ERROR] {item.source.name}: {item.error}")
        elif not errors_only:
            if item.target is None:
                raise ValueError("计划成员缺少目标")
            lines.append(_format_move(item.source.name, item.target.name, width))
    return "\n".join(lines)


def format_report(report: ExecutionReport) -> str:
    """渲染执行报告。

    Args:
        report: 本次执行、恢复或撤销的报告。
    Returns:
        逐成员展示实际位置变化的文本，并附带执行或恢复错误。
    """
    width = max(
        (_display_width(change.actual_path.name) for change in report.before.changes),
        default=0,
    )
    lines = []
    for before, after in zip(report.before.changes, report.after.changes):
        lines.append(
            _format_move(before.actual_path.name, after.actual_path.name, width)
        )
    if report.error is not None:
        lines.append(f"[ERROR] {report.error}")
    for error in report.recovery_errors:
        lines.append(f"[RECOVERY ERROR] {error}")
    return "\n".join(lines)
