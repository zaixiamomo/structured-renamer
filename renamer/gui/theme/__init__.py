"""主题入口：当前参数、主题管理，以及窗口身份配色。"""

from .manager import T, ThemeManager
from .tokens import IDENTITY_COUNT, IDENTITY_KEYS

__all__ = ["IDENTITY_COUNT", "IDENTITY_KEYS", "T", "ThemeManager"]
