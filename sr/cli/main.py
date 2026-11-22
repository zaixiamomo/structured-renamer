"""命令行参数、子命令分发与退出码。"""

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from sr import __version__
from sr.app.errors import ApplicationError, UnfinishedBatchError


def _write(text: str, stream: TextIO) -> None:
    """按输出流编码安全写出单行文本。"""
    if not text:
        return
    encoding = getattr(stream, "encoding", None)
    if encoding:
        text = text.encode(encoding, errors="backslashreplace").decode(encoding)
    stream.write(text + "\n")


def _use_color(stream: TextIO) -> bool:
    """按终端能力决定是否启用颜色。"""
    if not stream.isatty() or os.environ.get("TERM") == "dumb":
        return False
    if os.name != "nt":
        return True
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetConsoleMode.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.GetConsoleMode.restype = wintypes.BOOL
    kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.SetConsoleMode.restype = wintypes.BOOL
    handle = msvcrt.get_osfhandle(stream.fileno())
    flags = wintypes.DWORD()
    return kernel.GetConsoleMode(handle, ctypes.byref(flags)) and kernel.SetConsoleMode(
        handle, flags.value | 0x0004
    )


def _parser() -> argparse.ArgumentParser:
    """构造 run、undo、redo、log 子命令。"""
    parser = argparse.ArgumentParser(
        prog="sr", allow_abbrev=False, description="使用 YAML 规则递归重命名普通文件"
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser(
        "run",
        help="按规则整批改名",
        description="按规则整批改名；存在未完成批次时停止并提示",
        allow_abbrev=False,
    )
    run.add_argument("--dir", type=Path, required=True, help="待处理目录")
    run.add_argument("--rule", type=Path, required=True, help="YAML 规则文件")
    run.add_argument("--dry-run", action="store_true", help="只显示改名计划")
    run.add_argument("--no-color", action="store_true", help="禁用彩色输出")
    undo = commands.add_parser(
        "undo", help="撤销指定批次或最新批次", allow_abbrev=False
    )
    undo.add_argument(
        "--id",
        dest="batch_id",
        metavar="ID",
        help="指定 ID；支持短 ID 前缀，省略时撤销最新一次改名",
    )
    undo.add_argument("--dry-run", action="store_true", help="只显示撤销计划")
    undo.add_argument("--no-color", action="store_true", help="禁用彩色输出")
    redo = commands.add_parser(
        "redo", help="重做指定批次或最新撤销", allow_abbrev=False
    )
    redo.add_argument(
        "--id",
        dest="batch_id",
        metavar="ID",
        help="指定 ID；支持短 ID 前缀，省略时重做最新一次撤销",
    )
    redo.add_argument("--dry-run", action="store_true", help="只显示重做计划")
    redo.add_argument("--no-color", action="store_true", help="禁用彩色输出")
    log = commands.add_parser("log", help="查看改名记录", allow_abbrev=False)
    query = log.add_mutually_exclusive_group()
    query.add_argument("--dir", type=Path, help="只查看此目录历史")
    query.add_argument(
        "--id",
        dest="batch_id",
        metavar="ID",
        help="查看指定 ID 的逐文件内容；支持短 ID 前缀",
    )
    log.add_argument("--no-color", action="store_true", help="禁用彩色输出")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """执行一次 CLI 调用。

    Args:
        argv: 参数列表；省略时读取 sys.argv。
    Returns:
        退出码：0 成功，1 运行或计划错误，2 参数错误，130 安全取消。
    Raises:
        SystemExit: argparse 处理帮助、版本或无效参数时退出。
    """
    args = _parser().parse_args(argv)
    notice_color = _use_color(sys.stderr) and not args.no_color
    try:
        # 帮助与版本不加载插件、适配器和运行服务。
        from sr.bootstrap import assemble_application
        from sr.cli.report import (
            format_batch,
            format_failure,
            format_history,
            format_notice,
            format_unfinished,
        )

        color = _use_color(sys.stdout) and not args.no_color
        service = assemble_application()
        if args.command == "log":
            if args.batch_id is None:
                entries = service.history(args.dir)
                _write(format_history(entries, color=color), sys.stdout)
            else:
                batch = service.find_batch(args.batch_id)
                replay = batch.direction != "forward" or batch.status == "running"
                _write(format_batch(batch, color=color, replay=replay), sys.stdout)
            return 0
        if args.command == "run":
            result = service.rename(args.dir, args.rule, dry_run=args.dry_run)
        elif args.command == "undo":
            result = service.undo(batch_id=args.batch_id, dry_run=args.dry_run)
        else:
            result = service.redo(batch_id=args.batch_id, dry_run=args.dry_run)
        replay = args.command in ("undo", "redo")
        _write(
            format_batch(
                result,
                color=color,
                dry_run=args.dry_run,
                replay=replay,
            ),
            sys.stdout,
        )
        return int(result.counts(replay=replay).failed > 0)
    except KeyboardInterrupt:
        # 若已写入 running 批次，下一次 undo 或 redo 可继续恢复。
        _write(format_notice("已中断", color=notice_color), sys.stderr)
        return 130
    except UnfinishedBatchError as exc:
        _write(format_unfinished(exc.batch, color=notice_color), sys.stderr)
        return 1
    except ApplicationError as exc:
        _write(format_notice(str(exc), color=notice_color), sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI 边界统一报告运行错误
        _write(format_failure(str(exc), color=notice_color), sys.stderr)
        return 1
