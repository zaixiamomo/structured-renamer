"""规则编辑器的试跑交互：计时、取消意图和异步回写生命周期"""

from dataclasses import dataclass
from functools import partial

from PySide6.QtCore import QObject, QTimer, Signal

from renamer.app.rule_editing import RuleEditing

from ..execution_contracts import CapabilityRunner


@dataclass(frozen=True)
class RunDisplay:
    state: str = "idle"
    seconds: int = 0
    completed: bool = False


class RulePreviewTasks(QObject):
    """Qt 任务交互状态；结果是否有效由规则编辑工作集判断"""

    preview_changed = Signal()
    state_changed = Signal(str)

    def __init__(self, editing: RuleEditing, runner: CapabilityRunner, parent=None):
        super().__init__(parent)
        self._editing = editing
        self._runner = runner
        self._states: dict[str, RunDisplay] = {}
        self._timers: dict[str, QTimer] = {}
        self._closed = False

    def status(self, cap_id: str) -> RunDisplay:
        return self._states.get(cap_id, RunDisplay())

    def _set(self, cap_id: str, display: RunDisplay) -> None:
        self._states[cap_id] = display
        self.state_changed.emit(cap_id)

    def toggle(self, cap) -> None:
        if self._closed:
            return
        if self.status(cap.id).state == "running":
            self.cancel(cap.id)
            return
        started = self._editing.begin_preview(cap)
        self.reconcile()
        self.preview_changed.emit()
        if started is None:
            return
        ticket, inputs = started
        timer = self._timers.get(cap.id)
        if timer is None:
            timer = QTimer(self)
            timer.setInterval(1000)
            timer.timeout.connect(partial(self._tick, cap.id))
            self._timers[cap.id] = timer
        self._set(cap.id, RunDisplay("running"))
        timer.start()
        self._runner.run(
            cap.id,
            inputs,
            partial(self._complete, cap, ticket),
        )

    def _tick(self, cap_id: str) -> None:
        current = self.status(cap_id)
        if current.state != "running":
            return
        seconds = current.seconds + 1
        if seconds >= 15:
            self.cancel(cap_id)
        else:
            self._set(cap_id, RunDisplay("running", seconds))

    def cancel(self, cap_id: str) -> None:
        if self.status(cap_id).state != "running":
            return
        self._editing.cancel_preview(cap_id)
        self._timers[cap_id].stop()
        self._set(cap_id, RunDisplay("interrupted"))

    def reconcile(self) -> None:
        """样例或依赖变化后收起已失效的运行态，保留用户中断提示"""
        for cap_id, display in tuple(self._states.items()):
            if display.state == "running" and not self._editing.preview.is_running(
                cap_id
            ):
                self._timers[cap_id].stop()
                self._set(cap_id, RunDisplay(completed=True))

    def remove(self, cap_id: str) -> None:
        self._editing.cancel_preview(cap_id)
        timer = self._timers.pop(cap_id, None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()
        self._states.pop(cap_id, None)

    def clear(self) -> None:
        for cap_id in tuple(self._states):
            self.remove(cap_id)

    def _complete(self, cap, ticket, outputs) -> None:
        if self._closed:
            return
        if not self._editing.accept_preview(cap, ticket, outputs):
            return
        self.reconcile()
        self.preview_changed.emit()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._editing.invalidate_preview()
        for timer in self._timers.values():
            timer.stop()
