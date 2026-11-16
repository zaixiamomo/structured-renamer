"""配色系列：blue（蓝冷）、orange（橙暖）与 debug（高对比布局检视），共用同一套颜色键结构"""

from .tokens import ALL_COLOR_KEYS


def _validate(palette: dict) -> dict:
    """校验系列色值完备：必须恰好实现 tokens.ALL_COLOR_KEYS"""
    missing = set(ALL_COLOR_KEYS) - set(palette)
    if missing:
        raise ValueError(f"配色系列缺色值: {sorted(missing)}")
    return palette


# 内容标注色：编码数据类型分类，全系列共享同一引用
CONTENT_COLORS = {
    "color.content.string.base": "#8b5cf6",
    "color.content.string.strong": "#7c3aed",
    "color.content.string.soft": "#f1edfe",
    "color.content.int.base": "#12a394",
    "color.content.int.strong": "#0e8579",
    "color.content.int.soft": "#e2f5f1",
    "color.content.date.base": "#c2499a",
    "color.content.date.strong": "#a83480",
    "color.content.date.soft": "#fbe9f5",
    "color.content.enum.base": "#e0467a",
    "color.content.enum.strong": "#c22f5f",
    "color.content.enum.soft": "#fdeef3",
}


# 橙（暖）系列：交互 = 暖橙，身份 = 钢青灰
ORANGE = _validate(
    {
        # 画布
        "color.bg.base": "#f1eee7",
        "color.bg.surface": "#ffffff",
        "color.bg.surface2": "#f3efe5",
        "color.bg.surface3": "#ebe8e0",
        "color.border": "#eceae4",
        "color.border.strong": "#e0ded6",
        "color.text.primary": "#26261f",
        "color.text.secondary": "#8a8a80",
        "color.text.code": "#5a574d",
        "color.text.icon": "#c5c1b6",
        "color.text.icon.dir": "#a8a291",
        "color.text.arrow": "#bdb9ad",
        "color.n.bg": "#c8c4b8",
        "color.sb.thumb": "#d5d3cb",
        # 交互
        "color.accent": "#e8833a",
        "color.accent.strong": "#cf6a1f",
        "color.accent.hover": "#b85c14",
        "color.accent.soft": "#fcf0e4",
        "color.accent.softer": "#fef8f2",
        "color.on.accent": "#ffffff",
        # 语义
        "color.ok": "#2f9e5f",
        "color.warn": "#c98f2e",
        "color.warn.soft": "#fcf1df",
        "color.err": "#d24b3c",
        "color.err.soft": "#fcefed",
        # 身份（钢青灰族）
        "color.identity.0": "#a3b0bd",
        "color.identity.1": "#93a3b3",
        "color.identity.2": "#8497a9",
        "color.identity.3": "#758b9f",
        "color.identity.4": "#688095",
        # 内容标注（两系列一致，见模块级 CONTENT_COLORS）
        **CONTENT_COLORS,
    }
)

# 蓝（冷）系列：交互 = 蓝，身份 = 暖驼灰
BLUE = _validate(
    {
        # 画布
        "color.bg.base": "#eef0f4",
        "color.bg.surface": "#ffffff",
        "color.bg.surface2": "#edf1f8",
        "color.bg.surface3": "#e7ebf2",
        "color.border": "#d8dbe3",
        "color.border.strong": "#c9cdd8",
        "color.text.primary": "#22252b",
        "color.text.secondary": "#8a8f9a",
        "color.text.code": "#3a4150",
        "color.text.icon": "#b7bcc6",
        "color.text.icon.dir": "#98a0ac",
        "color.text.arrow": "#9aa0ab",
        "color.n.bg": "#a9afbc",
        "color.sb.thumb": "#c3c9d4",
        # 交互
        "color.accent": "#3563e9",
        "color.accent.strong": "#2952cc",
        "color.accent.hover": "#2246b5",
        "color.accent.soft": "#e8eefe",
        "color.accent.softer": "#f4f7fe",
        "color.on.accent": "#ffffff",
        # 语义
        "color.ok": "#1e9e6a",
        "color.warn": "#d97706",
        "color.warn.soft": "#fdf3e6",
        "color.err": "#dc2626",
        "color.err.soft": "#fdeaea",
        # 身份（暖驼灰族）
        "color.identity.0": "#b7aca2",
        "color.identity.1": "#a99e92",
        "color.identity.2": "#9b9082",
        "color.identity.3": "#8d8272",
        "color.identity.4": "#807463",
        # 内容标注（两系列一致，见模块级 CONTENT_COLORS）
        **CONTENT_COLORS,
    }
)

# 调试（debug）系列：布局/嵌套检视用，边界 > 内容
# - 分界线由 debug QSS/自绘层提供高对比（2px 深色实/虚线），负责「区分组件」；
# - 内容填充取「中低对比度」的柔和彩色：各层仍保留色相差异以便分辨归属，
#   但明度相近、饱和度收敛，不与边界抢注意力。文字用深色保证可读。
DEBUG = _validate(
    {
        # 画布（柔和分层，每层一个色相）
        "color.bg.base": "#e2e0dc",
        "color.bg.surface": "#ccd7ef",
        "color.bg.surface2": "#d3efdf",
        "color.bg.surface3": "#f2e2c8",
        "color.border": "#6f7685",
        "color.border.strong": "#000000",
        "color.text.primary": "#1d1f26",
        "color.text.secondary": "#565c6b",
        "color.text.code": "#14161c",
        "color.text.icon": "#7b8291",
        "color.text.icon.dir": "#636a7a",
        "color.text.arrow": "#6e7686",
        "color.n.bg": "#b6bdc9",
        "color.sb.thumb": "#a4adb9",
        # 交互（保留明确的蓝，标示可交互 / 选中）
        "color.accent": "#1f6feb",
        "color.accent.strong": "#1856c0",
        "color.accent.hover": "#113f8c",
        "color.accent.soft": "#e3eeff",
        "color.accent.softer": "#f0f6ff",
        "color.on.accent": "#ffffff",
        # 语义
        "color.ok": "#0d7a4f",
        "color.warn": "#8a5a00",
        "color.warn.soft": "#ffeab0",
        "color.err": "#c2271c",
        "color.err.soft": "#ffdcd6",
        # 身份（小面积亮彩，辨认缩略胶囊 / 色条归属）
        "color.identity.0": "#00a8c8",
        "color.identity.1": "#d01486",
        "color.identity.2": "#e89b00",
        "color.identity.3": "#2e9d4f",
        "color.identity.4": "#f2631c",
        # 内容标注（类型标注用，与正式系列一致）
        **CONTENT_COLORS,
    }
)

# 系列注册表（追加新系列时在此登记；注册顺序即主题循环顺序）
PALETTES = {
    "blue": BLUE,
    "orange": ORANGE,
    "debug": DEBUG,
}

# 初始默认系列
DEFAULT_SERIES = "blue"
