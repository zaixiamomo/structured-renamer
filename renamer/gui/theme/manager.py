"""应用主题：管理当前系列，将配色和结构参数应用到 QApplication。"""

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from .palette import DEFAULT_SERIES, PALETTES
from .qss import build_qss
from .tokens import FONT_FAMILY, STRUCTURAL

# 合法系列名
MODES = tuple(PALETTES)


def _families(qss_family: str) -> list:
    """把 QSS font-family 字符串解析为字族列表（剔除 generic 族）"""
    generic = {"sans-serif", "serif", "monospace", "cursive", "fantasy"}
    result = []
    for item in qss_family.split(","):
        name = item.strip().strip('"').strip("'")
        if name and name.lower() not in generic:
            result.append(name)
    return result


class ThemeManager(QObject):
    """主题管理器（单例），负责全局主题应用与系列热切换"""

    # 系列切换信号，参数为系列名（"orange" / "blue" / "debug"）
    theme_changed = Signal(str)

    _instance = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._series = DEFAULT_SERIES
        self._app = None

    @classmethod
    def instance(cls) -> "ThemeManager":
        """返回全局唯一实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def series(self) -> str:
        """当前系列：orange / blue / debug，默认 blue"""
        return self._series

    @property
    def tokens(self) -> dict:
        """当前系列合并令牌（结构令牌 + 系列色值）"""
        return {**STRUCTURAL, **PALETTES[self._series]}

    def set_series(self, series: str) -> None:
        """设置配色系列；若已 apply 过则自动热切换并发射 theme_changed"""
        if series not in MODES:
            raise ValueError(f"未知配色系列: {series!r}，应为 {MODES} 之一")
        if series == self._series:
            return
        self._series = series
        if self._app is not None:
            self.apply(self._app)
        self.theme_changed.emit(series)

    def toggle(self) -> None:
        """按注册表顺序循环系列（默认 blue → orange → debug → blue …）"""
        self.set_series(MODES[(MODES.index(self._series) + 1) % len(MODES)])

    def apply(self, app: QApplication | None = None) -> None:
        """生成并设置全局 QSS（含基础样式、字体、调色板）"""
        if app is None:
            app = QApplication.instance()
        if app is None:
            raise RuntimeError("ThemeManager.apply 需要可用的 QApplication 实例")
        self._app = app
        tokens = self.tokens
        app.setStyle("Fusion")
        app.setFont(_build_font(tokens))
        app.setPalette(_build_palette(tokens))
        app.setStyleSheet(build_qss(tokens, self._series))


def T(key: str):
    """取当前系列令牌值（颜色为 str，数值为 int）"""
    return ThemeManager.instance().tokens[key]


# 应用字体 / 调色板（QSS 之外的底座）


def _build_font(tokens: dict) -> QFont:
    """按字族与正文字阶构造应用字体"""
    font = QFont()
    font.setFamilies(_families(FONT_FAMILY))
    font.setStyleHint(QFont.SansSerif)
    font.setPixelSize(tokens["font.md"])
    # 避免 Windows 将小字号中文笔画强制对齐像素网格，保留平滑的字形轮廓。
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font


def _build_palette(tokens: dict) -> QPalette:
    """按令牌构造 QPalette（供 QStyle 绘制的箭头 / 图标等取色）"""
    c = lambda k: QColor(tokens[k])
    p = QPalette()
    p.setColor(QPalette.Window, c("color.bg.base"))
    p.setColor(QPalette.WindowText, c("color.text.primary"))
    p.setColor(QPalette.Base, c("color.bg.surface2"))
    p.setColor(QPalette.AlternateBase, c("color.bg.surface3"))
    p.setColor(QPalette.Text, c("color.text.primary"))
    p.setColor(QPalette.PlaceholderText, c("color.text.secondary"))
    p.setColor(QPalette.Button, c("color.bg.surface"))
    p.setColor(QPalette.ButtonText, c("color.text.primary"))
    p.setColor(QPalette.BrightText, c("color.on.accent"))
    p.setColor(QPalette.Highlight, c("color.accent"))
    p.setColor(QPalette.HighlightedText, c("color.on.accent"))
    p.setColor(QPalette.Link, c("color.accent"))
    p.setColor(QPalette.LinkVisited, c("color.accent.hover"))
    p.setColor(QPalette.ToolTipBase, c("color.bg.surface"))
    p.setColor(QPalette.ToolTipText, c("color.text.primary"))
    p.setColor(QPalette.Light, c("color.bg.surface"))
    p.setColor(QPalette.Midlight, c("color.bg.surface2"))
    p.setColor(QPalette.Mid, c("color.border.strong"))
    p.setColor(QPalette.Dark, c("color.border"))
    p.setColor(QPalette.Shadow, c("color.border"))
    disabled = c("color.n.bg")
    p.setColor(QPalette.Disabled, QPalette.Text, disabled)
    p.setColor(QPalette.Disabled, QPalette.WindowText, disabled)
    p.setColor(QPalette.Disabled, QPalette.ButtonText, disabled)
    return p
