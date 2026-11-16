"""CLI 前端：run/undo 两个子命令，人类可读输出，退出码 0/1/2"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from renamer.app import build_file_operations, build_service
from renamer.cli.report import (
    exit_code_for_report,
    format_issues,
    format_report,
    format_undo,
)
from renamer.core.model import PlanError

__all__ = ["main"]


class _UsageError(Exception):
    """参数/用法错误，映射退出码 2"""


class _Parser(argparse.ArgumentParser):
    """把 argparse 的 error 改为抛异常，使 main 返回退出码而非 sys.exit"""

    def error(self, message: str) -> None:
        raise _UsageError(message)


def _build_parser() -> _Parser:
    parser = _Parser(
        prog="renamer",
        description="领域插件化的文件结构化重命名工具",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    run_p = sub.add_parser("run", help="按规则批量改名（可 --dry-run 预览）")
    run_p.add_argument(
        "--library",
        required=True,
        type=Path,
        metavar="FILE",
        help="TOML 规则库路径，必须显式指定",
    )
    run_p.add_argument(
        "--rule",
        dest="rules",
        action="append",
        default=None,
        metavar="NAME",
        help="选择要应用的规则名，可重复；缺省应用库内全部规则（按声明序）",
    )
    run_p.add_argument(
        "--dir",
        dest="dirs",
        action="append",
        default=None,
        type=Path,
        metavar="DIR",
        help="目标目录，递归收集，可重复",
    )
    run_p.add_argument(
        "--dry-run",
        action="store_true",
        help="只预览不改名（不写 undo 日志）",
    )
    run_p.add_argument(
        "--undo-log",
        type=Path,
        default=None,
        metavar="FILE",
        help="覆盖 userdata/config.toml 中的撤销日志路径（默认 logs/undo_log.jsonl）",
    )
    run_p.add_argument(
        "paths",
        nargs="*",
        type=Path,
        metavar="PATH",
        help="目标文件或目录（与 --dir 一并收集）",
    )

    undo_p = sub.add_parser("undo", help="回滚（默认最近一次，幂等）")
    undo_p.add_argument(
        "--id",
        dest="log_id",
        default=None,
        metavar="LOG_ID",
        help="撤销指定批次 id；缺省最近一次",
    )
    undo_p.add_argument(
        "--undo-log",
        type=Path,
        default=None,
        metavar="FILE",
        help="覆盖 userdata/config.toml 中的撤销日志路径（默认 logs/undo_log.jsonl）",
    )
    return parser


def collect_files(dirs: Sequence[Path], paths: Sequence[Path]) -> list[Path]:
    """收集文件：--dir 目录递归 + 位置参数（文件或目录），跨来源去重保序"""
    files: list[Path] = []
    seen: set[Path] = set()
    for path in [*dirs, *paths]:
        if path.is_dir():
            candidates = sorted(p for p in path.rglob("*") if p.is_file())
        elif path.is_file():
            candidates = [path]
        else:
            raise _UsageError(f"路径不存在：{path}")
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                files.append(candidate)
    return files


def _run(args: argparse.Namespace) -> int:
    dirs = args.dirs or []
    paths = args.paths or []
    if not dirs and not paths:
        print("error: 需要至少一个 --dir 或文件路径", file=sys.stderr)
        return 2
    try:
        files = collect_files(dirs, paths)
    except _UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        service = build_service(args.library, undo_log_path=args.undo_log)
        report = service.run(args.rules or [], files, dry_run=args.dry_run)
    except PlanError as exc:
        print(format_issues(exc.issues), file=sys.stderr)
        return 2

    print(format_report(report))
    return exit_code_for_report(report)


def _undo(args: argparse.Namespace) -> int:
    try:
        operations = build_file_operations(args.undo_log)
        actual, restored, _records = operations.undo(args.log_id)
    except PlanError as exc:
        print(format_issues(exc.issues), file=sys.stderr)
        return 2
    print(format_undo(actual, restored))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI 入口：解析参数并分发到 run/undo，返回退出码 0/1/2"""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except _UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        parser.print_usage(sys.stderr)
        return 2

    if args.command == "run":
        return _run(args)
    return _undo(args)


if __name__ == "__main__":
    raise SystemExit(main())
