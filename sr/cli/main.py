"""sr 命令行入口。"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from sr import __version__
from sr.cli.report import format_plan, format_report


def _write(text: str, stream: TextIO) -> None:
    """按输出流编码安全写出单行文本。"""
    if not text:
        return
    encoding = getattr(stream, "encoding", None)
    if encoding:
        text = text.encode(encoding, errors="backslashreplace").decode(encoding)
    stream.write(text + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    """执行一次 CLI 调用。

    Args:
        argv: 参数列表；省略时读取 sys.argv。
    Returns:
        进程退出码：0 成功，1 运行或预览错误；参数错误由 argparse 以 2 退出。
    Raises:
        SystemExit: argparse 处理帮助、版本或无效参数时退出。
    """
    parser = argparse.ArgumentParser(
        prog="sr",
        description="使用 YAML 规则递归重命名普通文件。",
        epilog="每次命令重新计算；--undo 优先恢复未完成操作，否则撤销指定目录上一批改名。",
        allow_abbrev=False,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--dir", type=Path, required=True, help="待处理目录")
    parser.add_argument("--rule", type=Path, help="YAML 规则文件")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-out", action="store_true", help="计算并显示预览，不改名、不保存计划"
    )
    mode.add_argument(
        "--undo", action="store_true", help="恢复未完成操作，或撤销此目录上一批改名"
    )
    args = parser.parse_args(argv)
    if args.undo and args.rule is not None:
        parser.error("--undo 不需要 --rule")
    if not args.undo and args.rule is None:
        parser.error("需要 --rule")

    # 延迟导入，保证 --help/--version 不加载插件和适配器。
    from sr.bootstrap import assemble_application

    has_errors = False
    try:
        service = assemble_application()
        if args.undo:
            report = service.undo(args.dir)
        else:
            plan = service.prepare(args.dir, args.rule)
            has_errors = any(item.error is not None for item in plan.items)
            if args.dry_out:
                _write(format_plan(plan), sys.stdout)
                return int(has_errors)
            if has_errors:
                _write(format_plan(plan, errors_only=True), sys.stdout)
            error_code = 1
            report = service.execute(plan)
        _write(format_report(report), sys.stdout)
        return int(has_errors or report.error is not None)
    except Exception as exc:
        _write(f"[ERROR] {exc}", sys.stderr)
        return 1
