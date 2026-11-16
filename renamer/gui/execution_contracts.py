"""GUI 异步执行契约，结果由后台适配器在主线程交付"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from renamer.app import FileResult, Issue


@dataclass
class RunOutcome:
    items: list[FileResult]
    plan_error: list[Issue] | None = None
    message: str | None = None


class Executor(Protocol):
    def preview(
        self,
        paths: list[Path],
        rule_names: list[str],
        on_done: Callable[[RunOutcome], None],
    ) -> None: ...

    def apply(
        self,
        paths: list[Path],
        rule_names: list[str],
        on_done: Callable[[RunOutcome], None],
    ) -> None: ...

    def undo(self, on_done: Callable[[RunOutcome], None]) -> None: ...


class CapabilityRunner(Protocol):
    def run(
        self,
        cap_id: str,
        inputs: dict[str, str],
        on_done: Callable[[dict[str, str]], None],
    ) -> None: ...
