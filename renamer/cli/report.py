"""CLI 人类可读输出：Report 与 undo 结果转文本，并计算退出码"""

from __future__ import annotations

from renamer.core.model import Issue, Report, Status

__all__ = [
    "exit_code_for_report",
    "format_issue",
    "format_issues",
    "format_report",
    "format_undo",
]


def format_issue(issue: Issue) -> str:
    """单个 Issue 的人类可读文本"""
    return f"[{issue.level.value.upper()}] {issue.code}: {issue.message}"


def format_issues(issues: list[Issue]) -> str:
    """多个 Issue 的逐行文本"""
    return "\n".join(format_issue(i) for i in issues)


def format_report(report: Report) -> str:
    """Report 转人类可读文本：摘要行 + 逐文件明细"""
    summary = report.summary
    lines = [
        (
            f"log_id {report.log_id} | 总 {summary.total}："
            f"成功 {summary.success}、失败 {summary.failed}、"
            f"冲突 {summary.conflict}、跳过 {summary.skipped}"
        )
    ]
    for item in report.items:
        if item.status is Status.SUCCESS and item.target is not None:
            lines.append(f"  改名: {item.source.name} -> {item.target.name}")
            continue
        lines.append(f"  [{item.status.value}] {item.source.name}")
        for issue in item.issues:
            lines.append(f"        {format_issue(issue)}")
    return "\n".join(lines)


def format_undo(log_id: str | None, restored: int) -> str:
    """撤销结果转人类可读文本"""
    if restored == 0:
        return "无可撤销记录（已是最新状态或日志为空）"
    return f"已撤销批次 {log_id}，还原 {restored} 条"


def exit_code_for_report(report: Report) -> int:
    """报告转退出码：0 无 failed/conflict，1 有 failed/conflict"""
    if report.summary.failed or report.summary.conflict:
        return 1
    return 0
