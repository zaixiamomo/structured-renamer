"""批量改名用例：选择规则、求值文件，再提交文件变更"""

from __future__ import annotations

import itertools
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path

from renamer.core.compile import Plan, compile_rule
from renamer.core.model import (
    Capability,
    CapabilityFn,
    FileResult,
    Issue,
    Level,
    Library,
    PlanError,
    Report,
    ReportSummary,
    Rule,
    Status,
    UndoRecord,
)
from renamer.core.ports import Clock
from renamer.core.runtime import run_file

from .file_operations import FileOperations

__all__ = ["RenameService", "make_log_id"]

# 进程内单调递增序号，保证连续批次 log_id 唯一
_log_id_seq = itertools.count()


def make_log_id(clock: Callable[[], float]) -> str:
    """生成批次 log_id，进程内序号保证连续批次唯一"""
    ts = clock()
    dt = datetime.fromtimestamp(ts)  # noqa: DTZ006  # log_id 用本地时间，刻意不传 tz
    suffix = format(next(_log_id_seq) % 0x1000000, "06x")
    return dt.strftime("%Y%m%d-%H%M%S") + "-" + suffix


def _is_mismatch(result: FileResult) -> bool:
    """是否为解析模板不匹配导致的跳过"""
    return any(issue.code == "template_mismatch" for issue in result.issues)


def _summarize(items: Sequence[FileResult]) -> ReportSummary:
    """按状态统计汇总"""
    counts = Counter(item.status for item in items)
    return ReportSummary(
        total=len(items),
        success=counts[Status.SUCCESS],
        failed=counts[Status.FAILED],
        conflict=counts[Status.CONFLICT],
        skipped=counts[Status.SKIPPED],
    )


class RenameService:
    """使用已装配的能力与端口，编排批量改名、预览和撤销"""

    def __init__(
        self,
        *,
        library: Library,
        operations: FileOperations,
        capabilities: Mapping[str, Capability],
        calls: Mapping[str, CapabilityFn],
        clock: Clock | None = None,
    ) -> None:
        self._library = library
        self._operations = operations
        self._clock: Callable[[], float] = clock if clock is not None else time.time
        self._capabilities = capabilities
        self._calls = calls

    def with_library(self, library: Library) -> RenameService:
        """换库：GUI 会话内编辑的模板/规则实时生效"""
        self._library = library
        return self

    def run(
        self,
        rule_names: Sequence[str],
        paths: Sequence[Path],
        *,
        dry_run: bool = False,
    ) -> Report:
        """按多规则语义批量改名或预览，返回汇总 Report

        多规则对单文件按声明序逐个尝试，首个解析成功的规则生效，全部失败
        则该文件标记 SKIPPED（记 template_mismatch）

        Args:
            rule_names: 要应用的规则名序列，空则应用库内全部规则（声明序）
            paths: 源文件路径列表
            dry_run: 为真只预览不改名，不写撤销日志

        Returns:
            汇总 Report（含 ReportSummary 计数）

        Raises:
            PlanError: 规则名不存在或任一规则编译失败
        """
        rules = self._select_rules(rule_names)
        plans = self._compile_plans(rules)
        log_id = make_log_id(self._clock)

        items = [self._process_path(plans, path) for path in paths]

        if not dry_run:
            for item in items:
                if item.status is Status.SUCCESS:
                    self._operations.apply(item, log_id)

        return Report(log_id=log_id, summary=_summarize(items), items=items)

    def undo(
        self, log_id: str | None = None
    ) -> tuple[str | None, int, list[UndoRecord]]:
        """撤销本服务使用的文件操作日志，返回实际批次及还原记录"""
        return self._operations.undo(log_id)

    # 内部编排

    def _select_rules(self, rule_names: Sequence[str]) -> list[Rule]:
        """按名选取规则；空序列取全部（声明序）；缺失名抛 PlanError"""
        if not rule_names:
            return list(self._library.rules.values())
        selected: list[Rule] = []
        for name in rule_names:
            rule = self._library.rules.get(name)
            if rule is None:
                raise PlanError(
                    [
                        Issue(
                            level=Level.ERROR,
                            code="rule_not_found",
                            message=f"规则 {name!r} 不存在",
                        )
                    ]
                )
            selected.append(rule)
        return selected

    def _compile_plans(self, rules: Sequence[Rule]) -> list[Plan]:
        """编译全部选中规则为 Plan，任一失败聚合 issues 抛 PlanError"""
        plans: list[Plan] = []
        issues: list[Issue] = []
        for rule in rules:
            try:
                plans.append(compile_rule(rule, self._library, self._capabilities))
            except PlanError as exc:
                issues.extend(exc.issues)
        if issues:
            raise PlanError(issues)
        return plans

    def _process_path(self, plans: Sequence[Plan], path: Path) -> FileResult:
        """按声明序尝试各 plan，首个解析成功的生效；全部失败 SKIPPED"""
        for plan in plans:
            result = run_file(plan, path, self._calls, self._operations.filesystem)
            if result.status is Status.SKIPPED and _is_mismatch(result):
                continue  # 解析不匹配，换下一条规则
            return result
        return FileResult(
            source=path,
            target=None,
            status=Status.SKIPPED,
            issues=[
                Issue(
                    level=Level.ERROR,
                    code="template_mismatch",
                    message=f"没有规则匹配 {path.name!r}（全部解析模板不匹配）",
                )
            ],
        )
