"""设计令牌：系列无关的数值与颜色键契约"""

# 正文字族（QSS font-family 字符串）
FONT_FAMILY = (
    '"Segoe UI", "Microsoft YaHei", "Noto Sans CJK SC", '
    '"WenQuanYi Micro Hei", sans-serif'
)

# 等宽字族（QSS font-family 字符串）
MONO_FAMILY = '"Cascadia Code", "JetBrains Mono", "Consolas", monospace'

# 间距（4pt 基线，单位 px）

SPACING = {
    "space.1": 4,
    "space.2": 8,
}

# 圆角（单位 px）

RADIUS = {
    "radius.sm": 4,
    "radius.md": 8,
    "radius.lg": 12,
}

# 字阶 / 字重（单位 px / 无单位）

FONT = {
    "font.xs": 11,
    "font.sm": 12,
    "font.md": 13,
    "font.lg": 14,
    "font.weight.semibold": 600,
    "font.weight.bold": 700,
}

# 尺寸（单位 px）

SIZE = {
    "size.toolbar.h": 35,
    "size.bottombar.h": 35,
    "size.side_panel.w": 440,
    "size.side_panel.w.min": 260,
    "size.side_panel.w.max": 1000,
    "size.tree.min.w": 320,
    "size.scrollbar.w": 10,
    # 缩略列宽：仅容纳胶囊外轮廓，与滚动条解耦
    "size.thumbs.w": 20,
    "size.thumb.min": 18,
    "size.thumb.circle": 20,
    "size.tree.row.h": 26,
    "size.tree.indent": 10,
}

# 系列无关令牌（间距 / 圆角 / 字阶 / 尺寸）
STRUCTURAL = {**SPACING, **RADIUS, **FONT, **SIZE}

# 颜色键契约（五套颜色系统各守领地）

# 画布系统：底色 / 文字 / 边框
CANVAS_KEYS = (
    "color.bg.base",
    "color.bg.surface",
    "color.bg.surface2",
    "color.bg.surface3",
    "color.border",
    "color.border.strong",
    "color.text.primary",
    "color.text.secondary",
    "color.text.code",
    "color.text.icon",
    "color.text.icon.dir",
    "color.text.arrow",
    "color.n.bg",
    "color.sb.thumb",
)

# 交互系统：唯一强调色，只用于可交互处
INTERACTIVE_KEYS = (
    "color.accent",
    "color.accent.strong",
    "color.accent.hover",
    "color.accent.soft",
    "color.accent.softer",
    "color.on.accent",
)

# 语义系统：绿 / 琥珀 / 红，用于执行状态
SEMANTIC_KEYS = (
    "color.ok",
    "color.warn",
    "color.warn.soft",
    "color.err",
    "color.err.soft",
)

# 身份色族：低饱和，用于缩略块区分所属编辑窗口
IDENTITY_COUNT = 5
IDENTITY_KEYS = tuple(f"color.identity.{i}" for i in range(IDENTITY_COUNT))

# 内容标注色族：token 类型标注专用，类型对齐 FieldType（string / int / date / enum）
CONTENT_TYPES = ("string", "int", "date", "enum")
CONTENT_KEYS = tuple(
    f"color.content.{t}.{a}" for t in CONTENT_TYPES for a in ("base", "strong", "soft")
)

# 全部颜色键（合并视图，用于校验每套系列色值完备）
ALL_COLOR_KEYS = (
    CANVAS_KEYS + INTERACTIVE_KEYS + SEMANTIC_KEYS + IDENTITY_KEYS + CONTENT_KEYS
)
