"""文件树的行外观、命中尺寸及拖拽图；不读取控件或修改树状态。"""

from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap

from renamer.app import Status

from ..state.files import TreeNode
from ..state.status_style import STATUS_STYLE
from ..theme import T

# 箭头与复选框尺寸同时用于绘制和命中检测。
ARROW_W = 14
CHK = 15
ARROW_GAP = 2
GAP = 6
PAD_LEFT = 5
PAD_RIGHT = 10


def ghost_name(node: TreeNode) -> str | None:
    """预览改名时显示的旧名；无预览的节点只有一行。"""
    if node.is_dir or node.rename is None or node.rename == node.name:
        return None
    return node.name


def hit_area(node: TreeNode, depth: int, position: QPoint) -> str:
    """行内命中区域；第二行旧名只响应行操作。"""
    if position.y() >= int(T("size.tree.row.h")):
        return "body"
    x = PAD_LEFT + depth * int(T("size.tree.indent"))
    if node.is_dir and x <= position.x() < x + ARROW_W:
        return "arrow"
    x += ARROW_W + ARROW_GAP
    return "chk" if x <= position.x() < x + CHK else "body"


def paint_row(
    painter: QPainter,
    rect: QRect,
    node: TreeNode,
    depth: int,
    *,
    selected: bool,
    hovered: bool,
    status: Status | None,
    check_state: int,
) -> None:
    indent = int(T("size.tree.indent"))
    row_h = int(T("size.tree.row.h"))

    # 行底色优先级：状态 > 选中 > hover；幽灵行随条目整块同底色
    tint = None
    if status is not None:
        tint = QColor(T(STATUS_STYLE[status][0]))
    if tint is not None:
        painter.fillRect(rect, tint)
    elif selected:
        painter.fillRect(rect, QColor(T("color.accent.soft")))
    elif hovered:
        painter.fillRect(rect, QColor(T("color.bg.surface3")))

    x = rect.left() + PAD_LEFT + depth * indent

    # 箭头槽（目录显示三角，文件留空；槽位固定，保证同级文本对齐）
    if node.is_dir:
        _draw_arrow(painter, QRect(x, rect.top(), ARROW_W, row_h), node.open)
    x += ARROW_W + ARROW_GAP

    # 三态复选框（对齐首带，幽灵行无复选）
    chk_rect = QRect(x, rect.top() + (row_h - CHK) // 2, CHK, CHK)
    x += CHK + GAP
    _draw_checkbox(painter, chk_rect, check_state)

    # 名称文本（超长右省略）；预览态主标签显示目标名
    font = QFont(painter.font())
    font.setPixelSize(int(T("font.md")))
    font.setWeight(QFont.Weight.Normal)
    painter.setFont(font)
    color_key = (
        "color.accent.strong"
        if selected
        else "color.text.icon.dir"
        if node.is_dir
        else "color.text.primary"
    )
    text_w = max(1, rect.right() - PAD_RIGHT - x)
    main_band = QRect(rect.left(), rect.top(), rect.width(), row_h)
    _draw_name_line(
        painter,
        font,
        node.rename if ghost_name(node) is not None else node.name,
        color_key,
        x,
        main_band,
        text_w,
    )

    # 幽灵行：紧随其下的灰色删除线旧名（与主标签同缩进、同行文本宽）
    ghost = ghost_name(node)
    if ghost is not None:
        ghost_band = QRect(rect.left(), rect.top() + row_h, rect.width(), row_h)
        _draw_name_line(
            painter,
            font,
            ghost,
            "color.text.secondary",
            x,
            ghost_band,
            text_w,
            strike=True,
        )


def _draw_name_line(
    painter: QPainter,
    font: QFont,
    text: str,
    color_key: str,
    x: int,
    band_rect: QRect,
    text_w: int,
    *,
    strike: bool = False,
) -> None:
    """在单行带内绘制一个名称文本；strike=True 时带灰色删除线（预览幽灵旧名）"""
    fm = QFontMetrics(font)
    painter.setPen(QColor(T(color_key)))
    elided = fm.elidedText(text, Qt.TextElideMode.ElideRight, text_w)
    # 光学居中：字体 ascent 内含大段内部行距（CJK 字族尤甚），AlignVCenter 整框居中
    # 会把字形带压到行中线下方；改为按「cap-height 字形带」中心对齐行中线。
    baseline = band_rect.center().y() + fm.capHeight() / 2
    painter.drawText(QPointF(x, baseline), elided)
    if strike:
        # 删除线穿过字形带中线（CJK 占满全框，取 ascent 中点）
        sy = round(baseline - fm.ascent() / 2)
        painter.drawLine(QPoint(x, sy), QPoint(x + fm.horizontalAdvance(elided), sy))


def _draw_arrow(painter: QPainter, rect: QRect, open_: bool) -> None:
    """Windows 资源管理器风格箭头：收起 > / 展开 v（宽而浅的细线 chevron）"""
    cx, cy = rect.center().x(), rect.center().y()
    h, v = 4, 2  # 半宽 / 半深：横宽竖浅，避免展开 v 过深
    pen = QPen(QColor(T("color.text.arrow")), 1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    if open_:
        pts = [QPoint(cx - h, cy - v), QPoint(cx, cy + v), QPoint(cx + h, cy - v)]
    else:
        # 收起 > 是展开 v 的 90° 旋转（半宽/半深互换）：笔势同角，避免平扁
        pts = [QPoint(cx - v, cy - h), QPoint(cx + v, cy), QPoint(cx - v, cy + h)]
    painter.drawPolyline(pts)


def _draw_checkbox(painter: QPainter, rect: QRect, state: int) -> None:
    r = 4
    if state == 0:
        painter.setPen(QPen(QColor(T("color.border.strong")), 1.5))
        painter.setBrush(QColor(T("color.bg.surface")))
        painter.drawRoundedRect(rect, r, r)
    elif state == 2:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(T("color.accent.strong")))
        painter.drawRoundedRect(rect, r, r)
        pen = QPen(QColor(T("color.on.accent")), 1.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        cy = rect.center().y()
        # 勾号上下居中：两端点关于 cy 对称
        painter.drawPolyline(
            [
                QPoint(rect.left() + 4, cy + 1),
                QPoint(rect.left() + 6, cy + 3),
                QPoint(rect.left() + 11, cy - 3),
            ]
        )
    else:
        painter.setPen(QPen(QColor(T("color.accent")), 1.5))
        painter.setBrush(QColor(T("color.accent.soft")))
        painter.drawRoundedRect(rect, r, r)
        painter.setPen(QPen(QColor(T("color.accent.strong")), 1.8))
        cy = rect.center().y()
        painter.drawLine(QPoint(rect.left() + 3, cy), QPoint(rect.right() - 3, cy))


def drag_pixmap(name: str, font: QFont) -> QPixmap:
    """拖拽跟随图：文件名浮签（surface3 圆角底 + 主题文字）"""
    font = QFont(font)
    font.setPixelSize(int(T("font.md")))
    fm = QFontMetrics(font)
    text = name
    w = fm.horizontalAdvance(text) + 18
    h = fm.height() + 8
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(T("color.bg.surface3")))
    painter.drawRoundedRect(QRect(0, 0, w, h), 6, 6)
    painter.setFont(font)
    painter.setPen(QColor(T("color.text.primary")))
    painter.drawText(
        QRect(9, 0, w - 18, h),
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
        text,
    )
    painter.end()
    return pm
