"""应用层错误类型。"""


class ApplicationError(RuntimeError):
    """可直接展示给用户的运行错误。"""


class StateWriteError(ApplicationError):
    """状态持久化失败。"""
