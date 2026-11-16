"""全局控件外观：按基础控件、窗口、编辑页、规则控件及状态覆盖生成 QSS。"""

from .tokens import FONT_FAMILY, MONO_FAMILY


def build_qss(tokens: dict, series: str | None = None) -> str:
    """根据合并令牌字典生成全局 QSS；series 为 "debug" 时追加高对比描边覆盖层"""
    if not isinstance(tokens, dict) or "color.accent" not in tokens:
        raise ValueError("build_qss: tokens 必须是合并令牌字典（见 palette.py）")
    c = lambda k: tokens[k]
    s = lambda k: int(tokens[k])
    blocks = [
        _qss_base(c, s),
        _qss_skeleton(c, s),
        _qss_side_panel(c, s),
        _qss_rule_panel(c, s),
        _qss_status(c),
    ]
    if series == "debug":
        blocks.append(_qss_debug(s))
    return "\n".join(blocks)


def _qss_base(c, s) -> str:
    """基座：QWidget / QToolTip / QScrollBar / QSplitter"""
    return f"""
/* 基座 */
QWidget {{
    color: {c("color.text.primary")};
    font-family: {FONT_FAMILY};
    font-size: {s("font.md")}px;
}}
QMainWindow, QDialog {{ background-color: {c("color.bg.base")}; }}
#mainWindow {{ background-color: transparent; }}
QLabel {{
    background-color: transparent;
    color: {c("color.text.primary")};
}}
QFrame {{ border: none; }}

QToolTip {{
    background-color: {c("color.text.primary")};
    color: {c("color.bg.base")};
    border: 1px solid {c("color.border.strong")};
    border-radius: {s("radius.sm")}px;
    padding: {s("space.1")}px {s("space.2")}px;
    font-size: {s("font.sm")}px;
}}

/* 细滚动条（全局默认） */
QScrollBar:vertical {{
    background-color: transparent;
    width: 8px;
    margin: 2px 0px;
}}
QScrollBar::handle:vertical {{
    background-color: {c("color.sb.thumb")};
    min-height: 24px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{ background-color: {c("color.text.secondary")}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
    border: none;
    background: none;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QScrollBar:horizontal {{
    background-color: transparent;
    height: 8px;
    margin: 0px 2px;
}}
QScrollBar::handle:horizontal {{
    background-color: {c("color.sb.thumb")};
    min-width: 24px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{ background-color: {c("color.text.secondary")}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
    border: none;
    background: none;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}

QSplitter::handle {{ background-color: {c("color.border")}; }}
/* 抽屉手柄：drawerHandleLeft 0 宽隐藏，drawerHandleSeam 自绘接缝 */
#drawerSplitter::handle {{ background-color: {c("color.bg.base")}; }}
#drawerHandleLeft {{ width: 0px; }}
#drawerHandleSeam {{ background-color: {c("color.bg.surface")}; }}
"""


def _qss_skeleton(c, s) -> str:
    """三分区骨架：顶栏 / 主区 / 底栏，只应用画布系统颜色"""
    return f"""
/* 三分区骨架 */
#mainRoot {{
    background-color: {c("color.bg.surface")};
    border: 1px solid {c("color.border.strong")};
    border-radius: {s("radius.lg")}px;
}}
#topbar {{
    background-color: {c("color.bg.surface")};
    border-bottom: 1px solid {c("color.border")};
    border-top-left-radius: {s("radius.lg")}px;
    border-top-right-radius: {s("radius.lg")}px;
    min-height: {s("size.toolbar.h")}px;
    max-height: {s("size.toolbar.h")}px;
}}
#topbar QLabel[role="brand"] {{
    background-color: transparent;
    color: {c("color.text.primary")};
    font-size: {s("font.md")}px;
    font-weight: {s("font.weight.bold")};
}}
#topbar QPushButton[role="tb"], #topbar QPushButton[role="tb-primary"] {{
    background-color: transparent;
    border: none;
    border-radius: 7px;
    color: {c("color.text.primary")};
    font-size: {s("font.sm")}px;
    padding: 0px 10px;
    outline: none;
}}
#topbar QPushButton[role="tb"]:hover {{ background-color: {c("color.bg.surface3")}; }}
#topbar QPushButton[role="tb-primary"] {{
    background-color: {c("color.accent.strong")};
    color: {c("color.on.accent")};
    font-weight: {s("font.weight.semibold")};
}}
#topbar QPushButton[role="tb-primary"]:hover {{ background-color: {c("color.accent.hover")}; }}
#topbar QPushButton[role="winctl"], #topbar QPushButton[role="winctl-close"] {{
    background-color: transparent;
    border: none;
    border-radius: {s("radius.sm")}px;
    color: {c("color.text.icon")};
    font-size: {s("font.lg")}px;
    padding: 0px;
    outline: none;
}}
#topbar QPushButton[role="winctl"]:hover,
#topbar QPushButton[role="winctl-close"]:hover {{
    background-color: {c("color.bg.surface3")};
    color: {c("color.text.primary")};
}}
#topbar #brandDot {{
    background-color: {c("color.accent")};
    border: none;
    border-radius: 4px;
    padding: 0px;
}}
#topbar #brandDot:hover {{ background-color: {c("color.accent.hover")}; }}
#topbar #tbSep {{ background-color: {c("color.border")}; }}
#bottomBar {{
    background-color: {c("color.bg.surface")};
    border-top: 1px solid {c("color.border")};
    border-bottom-left-radius: {s("radius.lg")}px;
    border-bottom-right-radius: {s("radius.lg")}px;
    min-height: {s("size.bottombar.h")}px;
    max-height: {s("size.bottombar.h")}px;
}}
#bottomBar QLabel {{
    background-color: transparent;
    color: {c("color.text.secondary")};
    font-size: {s("font.sm")}px;
}}
#mainArea {{ background-color: {c("color.bg.base")}; }}
#treeArea {{ background-color: {c("color.bg.surface2")}; }}
/* 主区两列分色：文件树列 surface2、侧边窗口列 surface，缩略列自绘接缝 */
#sidePanelArea {{
    background-color: {c("color.bg.surface")};
}}
#sidePanelHead {{
    background-color: {c("color.bg.surface")};
}}
/* 头部分隔线：1px 细线，两侧留 12px 空白 */
#sidePanelDividerRow {{ background-color: transparent; }}
#sidePanelDivider {{ background-color: {c("color.border")}; }}
#sidePanelBody {{
    background-color: transparent;
    border: none;
}}
#sidePanelViewport {{ background-color: {c("color.bg.surface")}; }}
#sidePanelStack, #blankPanel, #sidePanelPage {{ background-color: transparent; }}
"""


def _qss_side_panel(c, s) -> str:
    """侧面板与面板内容"""
    return f"""
/* 侧面板与面板 */
#sidePanelHead QLabel[role="side-panel-kind"] {{
    background-color: transparent;
    color: {c("color.text.primary")};
    font-size: {s("font.md")}px;
    font-weight: {s("font.weight.bold")};
}}
#sidePanelHead QLineEdit[role="side-panel-title-edit"] {{
    background-color: transparent;
    border: none;
    border-bottom: 1px solid {c("color.text.secondary")};
    color: {c("color.text.secondary")};
    font-size: {s("font.md")}px;
    padding: 0px;
    selection-background-color: {c("color.accent")};
    selection-color: {c("color.on.accent")};
}}
#sidePanelHead QLineEdit[role="side-panel-title-edit"]:focus {{
    border-bottom: 1px solid {c("color.accent")};
    color: {c("color.text.primary")};
}}
#sidePanelColor {{
    background-color: {c("color.accent")};
    border: none;
    border-radius: 1px;
}}
QPushButton[role="d-btn"] {{
    background-color: {c("color.bg.surface")};
    color: {c("color.text.secondary")};
    border: 1px solid {c("color.border")};
    border-radius: 6px;
    padding: 4px 9px;
    font-size: {s("font.sm")}px;
    outline: none;
}}
QPushButton[role="d-btn"]:hover {{
    color: {c("color.accent.strong")};
    border-color: {c("color.accent")};
    background-color: {c("color.accent.softer")};
}}
QPushButton[role="d-btn-primary"] {{
    background-color: {c("color.accent.strong")};
    color: {c("color.on.accent")};
    border: none;
    border-radius: 6px;
    padding: 4px 9px;
    font-weight: {s("font.weight.semibold")};
    font-size: {s("font.sm")}px;
    outline: none;
}}
QPushButton[role="d-btn-primary"]:hover {{ background-color: {c("color.accent.hover")}; }}

QLabel[role="panel-title"] {{
    background-color: transparent;
    color: {c("color.text.secondary")};
    font-size: {s("font.xs")}px;
}}
QLabel[role="note"] {{
    background-color: transparent;
    color: {c("color.text.secondary")};
    font-size: {s("font.xs")}px;
    line-height: 1.7;
}}
QLabel[role="preview"] {{
    background-color: transparent;
    color: {c("color.text.code")};
    border: none;
    font-family: {MONO_FAMILY};
    font-size: {s("font.xs")}px;
    line-height: 1.8;
}}

/* 模板面板三区：侧窗口底色 surface，内容块 surface2，细线框划分 */
QWidget[role="match-pane"] {{
    background-color: {c("color.bg.surface2")};
    border: 1px solid {c("color.border")};
    border-radius: 10px;
}}
QWidget[role="tok-row"] {{ background-color: transparent; }}
QLabel[role="tok-seq"] {{
    background-color: transparent;
    color: {c("color.text.secondary")};
    font-family: {MONO_FAMILY};
    font-size: {s("font.xs")}px;
}}
QLabel[role="tok-raw"] {{
    background-color: transparent;
    color: {c("color.text.secondary")};
    font-size: {s("font.sm")}px;
}}
QLineEdit[role="tok-token"] {{
    background-color: transparent;
    border: none;
    border-bottom: 1px solid {c("color.border.strong")};
    color: {c("color.text.primary")};
    font-size: {s("font.sm")}px;
    padding: 1px 0px;
    selection-background-color: {c("color.accent")};
    selection-color: {c("color.on.accent")};
}}
QLineEdit[role="tok-token"]:focus {{ border-bottom: 1px solid {c("color.accent")}; }}
QComboBox[role="tok-type"] {{
    background-color: transparent;
    border: none;
    color: {c("color.text.primary")};
    font-size: {s("font.sm")}px;
    padding: 1px 2px;
    outline: none;
}}
QComboBox[role="tok-type"]:hover {{ color: {c("color.accent.strong")}; }}
QComboBox[role="tok-type"] QAbstractItemView {{
    background-color: {c("color.bg.surface")};
    color: {c("color.text.primary")};
    border: 1px solid {c("color.border")};
    selection-background-color: {c("color.bg.surface3")};
    selection-color: {c("color.accent.strong")};
    outline: none;
}}
QLineEdit[role="tok-values"] {{
    background-color: {c("color.bg.surface")};
    color: {c("color.text.code")};
    border: 1px solid {c("color.border")};
    border-radius: 5px;
    padding: 1px 6px;
    font-family: {MONO_FAMILY};
    font-size: {s("font.xs")}px;
    selection-background-color: {c("color.accent")};
    selection-color: {c("color.on.accent")};
}}
QLineEdit[role="tok-values"]:focus {{ border-color: {c("color.accent")}; }}
QPushButton[role="tok-del"], QPushButton[role="tok-add"] {{
    background-color: transparent;
    border: none;
    border-radius: 4px;
    color: {c("color.text.icon")};
    font-size: {s("font.sm")}px;
    padding: 0px 5px;
    outline: none;
}}
/* 全角加号的笔画范围偏小，增大字号补偿视觉大小。 */
QPushButton[role="tok-add"] {{ font-size: {s("font.sm") * 5 // 3}px; }}
QPushButton[role="tok-del"]:hover {{
    background-color: {c("color.err.soft")};
    color: {c("color.err")};
}}
QPushButton[role="tok-add"]:hover {{
    background-color: {c("color.accent.soft")};
    color: {c("color.accent.strong")};
}}
QPlainTextEdit[role="template-edit"] {{
    background-color: {c("color.bg.surface")};
    color: {c("color.text.code")};
    border: 1px solid {c("color.border")};
    border-radius: 6px;
    padding: 6px;
    font-family: {MONO_FAMILY};
    font-size: {s("font.xs")}px;
    selection-background-color: {c("color.accent")};
    selection-color: {c("color.on.accent")};
}}
QPlainTextEdit[role="template-edit"]:focus {{ border-color: {c("color.accent")}; }}
/* 模板/规则面板末卡共用的只读 TOML（TomlEdit.readonly 统一设此 objectName）：
   并入卡片底色 surface2、去边框，去掉通用 role 的 6px padding，文本与卡内
   其余内容同左缘对齐（卡片边距由 EditorCard 布局承担） */
QPlainTextEdit#templateTomlEdit {{
    background-color: {c("color.bg.surface2")};
    border: none;
    border-radius: 0px;
    padding: 0px;
}}

QMenu {{
    background-color: {c("color.bg.surface")};
    color: {c("color.text.primary")};
    border: 1px solid {c("color.border")};
    border-radius: 8px;
    padding: 5px;
    font-size: {s("font.sm")}px;
}}
QMenu::item {{ padding: 6px 18px; border-radius: 5px; }}
QMenu::item:selected {{ background-color: {c("color.bg.surface3")}; color: {c("color.accent.strong")}; }}
QMenu::item:disabled {{ color: {c("color.n.bg")}; }}
QMenu::separator {{ height: 1px; background-color: {c("color.border")}; margin: 4px 8px; }}
"""


def _qss_rule_panel(c, s) -> str:
    """规则面板：token 词组件 / 能力槽位 / 组合区 / 连接词输入"""
    return f"""
/* 规则面板：token 词组件 / 能力 / 组合 */
QFrame[role="t-chip"] {{
    border-radius: 6px;
}}
QFrame[role="t-chip"] QLabel, QFrame[role="t-chip"] QPushButton {{
    background-color: transparent;
}}
/* 类型色（激活/未激活状态色在其后覆盖） */
QFrame[role="t-chip"][tch="string"] {{ background-color: {c("color.content.string.soft")}; border: 1px solid {c("color.content.string.base")}; }}
QFrame[role="t-chip"][tch="int"]    {{ background-color: {c("color.content.int.soft")};    border: 1px solid {c("color.content.int.base")}; }}
QFrame[role="t-chip"][tch="date"]   {{ background-color: {c("color.content.date.soft")};   border: 1px solid {c("color.content.date.base")}; }}
QFrame[role="t-chip"][tch="enum"]   {{ background-color: {c("color.content.enum.soft")};   border: 1px solid {c("color.content.enum.base")}; }}
QLabel[role="t-chip-name"] {{
    color: {c("color.text.primary")};
    font-size: {s("font.xs")}px;
    font-weight: {s("font.weight.semibold")};
}}
QFrame[role="t-chip"][tch="string"] QLabel[role="t-chip-name"] {{ color: {c("color.content.string.strong")}; }}
QFrame[role="t-chip"][tch="int"]    QLabel[role="t-chip-name"] {{ color: {c("color.content.int.strong")}; }}
QFrame[role="t-chip"][tch="date"]   QLabel[role="t-chip-name"] {{ color: {c("color.content.date.strong")}; }}
QFrame[role="t-chip"][tch="enum"]   QLabel[role="t-chip-name"] {{ color: {c("color.content.enum.strong")}; }}
/* 已激活：统一为主题色 accent */
QFrame[role="t-chip"][tstate="active"] {{
    background-color: {c("color.accent.soft")};
    border: 1px solid {c("color.accent")};
}}
QFrame[role="t-chip"][tstate="active"] QLabel[role="t-chip-name"] {{ color: {c("color.accent.strong")}; }}
/* 未激活：灰态，左键激活后转主题色 */
QFrame[role="t-chip"][tstate="inactive"] {{
    background-color: {c("color.bg.surface3")};
    border: 1px solid {c("color.border.strong")};
}}
QFrame[role="t-chip"][tstate="inactive"] QLabel[role="t-chip-name"] {{ color: {c("color.text.secondary")}; }}
QLabel[role="parse-lit"] {{
    background-color: transparent;
    color: {c("color.text.secondary")};
    font-family: {MONO_FAMILY};
    font-size: {s("font.xs")}px;
}}
/* 划词区：放大字符及对应命中区域，便于精确拖选 */
WordCanvas {{ font-size: 14px; }}

/* 组合渲染编辑区：无边框无内缩，底色与卡片(match-pane surface2)一致融为一体 */
QTextEdit[role="compose-edit"] {{
    background-color: {c("color.bg.surface2")};
    color: {c("color.text.code")};
    border: none;
    border-radius: 0px;
    padding: 0px;
    font-family: {MONO_FAMILY};
    font-size: {s("font.md")}px;
    selection-background-color: {c("color.accent")};
    selection-color: {c("color.on.accent")};
}}
QTextEdit[role="compose-edit"]:focus {{ border: none; }}

/* 解析模板 / 补充能力 / 格式函数下拉：透明背景，仅保留下划线，悬停高亮 */
QComboBox[role="select-ghost"] {{
    background-color: transparent;
    border: none;
    border-bottom: 1px solid {c("color.border.strong")};
    color: {c("color.text.primary")};
    font-size: {s("font.sm")}px;
    padding: 1px 2px;
    outline: none;
}}
QComboBox[role="select-ghost"]:hover {{ color: {c("color.accent.strong")}; border-bottom: 1px solid {c("color.accent")}; }}
QComboBox[role="select-ghost"] QAbstractItemView {{
    background-color: {c("color.bg.surface")};
    color: {c("color.text.primary")};
    border: 1px solid {c("color.border")};
    selection-background-color: {c("color.bg.surface3")};
    selection-color: {c("color.accent.strong")};
    outline: none;
}}

/* 能力输入 / 输出槽位 */
QFrame[role="slot"] {{
    background-color: {c("color.bg.surface2")};
    border: 1px dashed {c("color.border.strong")};
    border-radius: 6px;
}}
QFrame[role="slot"][state="bound"] {{
    background-color: {c("color.accent.soft")};
    border: 1px solid {c("color.accent")};
}}
QFrame[role="slot"][state="done"] {{
    background-color: {c("color.accent.soft")};
    border: 1px solid {c("color.accent")};
}}
/* 产出未激活：灰态，左键激活转主题色 */
QFrame[role="slot"][state="done-off"] {{
    background-color: {c("color.bg.surface3")};
    border: 1px solid {c("color.border.strong")};
}}
QLabel[role="slot-cap"] {{
    background-color: transparent;
    color: {c("color.text.secondary")};
    font-family: {MONO_FAMILY};
    font-size: {s("font.xs")}px;
}}
QFrame[role="slot"][state="bound"] QLabel[role="slot-cap"] {{ color: {c("color.accent.strong")}; }}
QFrame[role="slot"][state="done"] QLabel[role="slot-cap"] {{ color: {c("color.accent.strong")}; }}
QFrame[role="slot"][state="done-off"] QLabel[role="slot-cap"] {{ color: {c("color.text.secondary")}; }}
QLabel[role="slot-val"] {{
    background-color: transparent;
    color: {c("color.text.secondary")};
    font-family: {MONO_FAMILY};
    font-size: {s("font.xs")}px;
}}
QFrame[role="slot"][state="done"] QLabel[role="slot-val"] {{
    color: {c("color.accent.strong")};
    font-weight: {s("font.weight.semibold")};
}}
QFrame[role="slot"][state="done-off"] QLabel[role="slot-val"] {{
    color: {c("color.text.secondary")};
}}
QFrame[role="slot"][state="bound"] QLabel[role="slot-val"] {{ color: {c("color.text.primary")}; }}
/* 能力块：一个能力一个块，去框成行、块顶细线分隔 */
QFrame[role="cap-block"] {{
    background-color: transparent;
    border: none;
    border-top: 1px solid {c("color.border")};
    border-radius: 0px;
}}
QLabel[role="cap-title"] {{
    background-color: transparent;
    color: {c("color.text.primary")};
    font-size: {s("font.sm")}px;
    font-weight: {s("font.weight.semibold")};
}}

/* 能力块「运行」按钮运行态：运行=黄、中断=红、成功回蓝（默认 accent） */
QPushButton[role="d-btn-primary"][runstate="running"],
QPushButton[role="d-btn-primary"][runstate="running"]:hover {{
    background-color: {c("color.warn")};
    color: {c("color.text.primary")};
}}
QPushButton[role="d-btn-primary"][runstate="interrupted"],
QPushButton[role="d-btn-primary"][runstate="interrupted"]:hover {{
    background-color: {c("color.err")};
    color: {c("color.on.accent")};
}}

/* 组合卡段间分隔细线（预览 / 编辑 / 词池，与能力块顶线同宽同色） */
QFrame[role="rule-hr"] {{
    background-color: {c("color.border")};
    border: none;
    min-height: 1px;
    max-height: 1px;
}}

/* 原位沿用宿主卡片的背景与圆角；冻结时使用实色背景遮挡下层内容。 */
QWidget[role="frozen-section"] {{
    background-color: transparent;
    border: none;
}}
QWidget[role="frozen-section"][state="pin"] {{
    background-color: {c("color.bg.surface2")};
    border-left: 1px solid {c("color.border")};
    border-right: 1px solid {c("color.border")};
}}
QWidget[role="frozen-section"][edge="bottom"][state="pin"][corner="round"] {{
    border-top: 1px solid {c("color.border")};
    border-top-left-radius: {s("radius.md")}px;
    border-top-right-radius: {s("radius.md")}px;
}}
QWidget[role="frozen-section"][edge="top"][state="pin"][corner="round"] {{
    border-bottom: 1px solid {c("color.border")};
    border-bottom-left-radius: {s("radius.md")}px;
    border-bottom-right-radius: {s("radius.md")}px;
}}
QFrame[role="frozen-divider"] {{
    background-color: {c("color.border")};
    border: none;
    min-height: 1px;
    max-height: 1px;
}}

/* 主按钮禁用态 */
QPushButton[role="d-btn-primary"]:disabled {{
    background-color: {c("color.n.bg")};
    color: {c("color.bg.surface")};
}}
"""


def _qss_status(c) -> str:
    """语义状态色后置，覆盖同优先级的 QLabel role 默认色。"""
    return f"""
/* 语义状态：组件只设置 status，颜色随主题统一刷新 */
QLabel[status="ok"] {{ color: {c("color.ok")}; }}
QLabel[status="warn"] {{ color: {c("color.warn")}; }}
QLabel[status="err"] {{ color: {c("color.err")}; }}
"""


def _qss_debug(s) -> str:
    """调试主题覆盖层：不同区域用不同高对比色描边（重叠处靠色相再区分一档）

    内容填充为低对比柔和色；边界每个区域专属一种「深饱和色」2px 实线。相邻
    区域的边各自成色，共享接缝处呈双色，能看出两边各自是谁；内部同底色区域
    （画布 / TOML / 词流行）用同族深色虚线再标一档。
    """
    return f"""
/* Debug 主题：分区高对比描边（每区一色，重叠区双色衬托） */
/* 顶底 Chrome */
#topbar {{
    border: 2px solid #d81b60;
    border-top-left-radius: {s("radius.lg")}px;
    border-top-right-radius: {s("radius.lg")}px;
}}
#bottomBar {{
    border: 2px solid #d81b60;
    border-bottom-left-radius: {s("radius.lg")}px;
    border-bottom-right-radius: {s("radius.lg")}px;
}}

/* 抽屉三列：树=绿 / 缩略列=紫（自绘层补框）/ 侧面板=青 */
#treeArea {{ border: 2px solid #2e7d32; }}
#sidePanelArea {{ border: 2px solid #00838f; }}

/* 侧面板内：头=橙（与下方正文区靠分隔线区分） */
#sidePanelHead {{ border: 2px solid #e65100; }}
#sidePanelDivider {{ background-color: #37474f; }}

/* 编辑器卡片=红实线；卡内同底色区各自再用深色虚线 */
QWidget[role="match-pane"] {{ border: 2px solid #c62828; }}
QPlainTextEdit#templateTomlEdit {{
    border: 1.5px dashed #283593;
    border-radius: 0px;
}}
QWidget[role="tok-row"] {{ border-bottom: 1px dotted #607d8b; }}
QFrame[role="cap-block"] {{
    border: 1px dashed #607d8b;
    border-top: 2px dashed #37474f;
}}
"""
