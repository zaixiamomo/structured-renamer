"""QApplication 装配 + 主题应用 + 主窗口启动"""

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QMessageBox

from renamer.adapters.config import load_config
from renamer.adapters.library_file import LibraryFile
from renamer.app import build_authoring_service, build_service
from renamer.app.capability_trial import CapabilityTrial
from renamer.app.composition import capability_calls
from renamer.app.session import AuthoringSession
from renamer.core.model import PlanError

from .theme import ThemeManager

__all__ = ["create_app", "run"]


def create_app(argv=None) -> QApplication:
    """装配 QApplication 并应用默认主题（blue 系列）"""
    app = QApplication(argv if argv is not None else [])
    app.setApplicationName("structured-renamer")
    ThemeManager.instance().apply(app)
    return app


def run() -> int:
    """启动主窗口并进入事件循环，返回进程退出码"""
    app = create_app()
    from .execution import ServiceCapabilityRunner, ServiceExecutor
    from .state.session_store import SessionStore
    from .views.main_window import MainWindow

    # 批量运行与编辑试运行分别持有能力实例，保留各自的缓存生命周期
    try:
        config = load_config()
        service = build_service(config=config)
    except PlanError as exc:
        QMessageBox.critical(None, "配置错误", str(exc))
        return 2
    authoring_session = AuthoringSession(LibraryFile(config.library_path))
    authoring_session.load()
    session = SessionStore(authoring_session, app)
    window = MainWindow(
        executor=ServiceExecutor(service, session),
        capability_runner=ServiceCapabilityRunner(CapabilityTrial(capability_calls())),
        authoring=build_authoring_service(),
        session=session,
    )
    tm = ThemeManager.instance()
    QShortcut(QKeySequence("F5"), window, activated=tm.toggle)
    window.show()
    return app.exec()
