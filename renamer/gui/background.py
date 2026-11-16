"""Qt 后台任务桥：在线程池执行，将结果交付到主线程"""

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _Task(QRunnable):
    def __init__(self, work, on_done, on_error, signal):
        super().__init__()
        self._work = work
        self._on_done = on_done
        self._on_error = on_error
        self._signal = signal

    def run(self) -> None:
        try:
            payload = self._work()
        except Exception as exc:  # noqa: BLE001 后台异常由用例指定的策略转换
            payload = self._on_error(exc)
        self._signal.emit((self._on_done, payload))


class BackgroundWorker(QObject):
    _task_done = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._task_done.connect(self._deliver)

    def submit(self, work, on_done, on_error) -> None:
        QThreadPool.globalInstance().start(
            _Task(work, on_done, on_error, self._task_done)
        )

    def _deliver(self, packed) -> None:
        on_done, payload = packed
        on_done(payload)
