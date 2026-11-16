"""侧边抽屉：文件树 + 窗口缩略列 + 编辑侧面板 + QSplitter + 滑动动画"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QSplitter,
    QWidget,
)

from ..state.window import WindowManager
from ..theme import T
from .drawer_shot import DrawerShot
from .side_panel import SidePanel
from .thumbs_column import ThumbsColumn

__all__ = ["Drawer"]


class Drawer(QSplitter):
    """侧边抽屉（缩略列 + 面板 + 滑动动画），自身即 QSplitter"""

    # 黄金比例（文件树:抽屉的默认排布取它）
    _PHI = 1.61803398875

    def __init__(self, manager: WindowManager, tree: QWidget, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._manager = manager
        self.setObjectName("drawerSplitter")
        self.setChildrenCollapsible(False)
        # 手柄宽 0：树/缩略列/面板两列分色，边界由缩略列发丝线自绘承担，无需分割槽位
        self.setHandleWidth(0)

        self.addWidget(tree)

        # 三段：文件树 | 窗口缩略列 | 面板；缩略列固定宽，拖拽增宽只作用于面板
        self._thumbs = ThumbsColumn(manager)
        self._side_panel = SidePanel(manager)
        body = QWidget()
        body.setObjectName("drawerArea")
        self._drawer_lay = QHBoxLayout(body)
        self._drawer_lay.setContentsMargins(0, 0, 0, 0)
        self._drawer_lay.setSpacing(0)
        self._drawer_lay.addWidget(self._side_panel)
        self.addWidget(self._thumbs)
        self.addWidget(body)
        # 树与缩略列手柄：0 宽隐藏（同底融合，无分隔）
        self.handle(1).setObjectName("drawerHandleLeft")
        self.handle(1).setFixedWidth(0)
        # 缩略列与面板手柄：恒 0，拉伸触发边 = 缩略列自身（resize_started/moved/finished
        # 信号由本类换算抽屉宽）
        self.handle(2).setObjectName("drawerHandleSeam")
        self.handle(2).setFixedWidth(0)
        self.handle(2).setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.setStretchFactor(0, 1)  # 窗口增宽时文件树吸收多余空间
        self.setStretchFactor(2, 0)  # 抽屉保持当前宽度

        # 抽屉展开宽度记忆（拖拽调宽后收起再展开恢复），随 splitterMoved 更新
        self._side_width = int(T("size.side_panel.w"))
        # 是否手动拖拽过抽屉：未拖拽前展开始终按黄金比例（文件树:抽屉 = φ:1）排布
        self._side_adjusted = False
        self._side_visible = False
        # 抽屉 splitter 手柄是否正在被拖拽（主窗口据此显示横向缩放光标与记忆宽度）
        self.dragging = False
        # 接缝拖拽状态：独立于 dragging，frameless 过滤器在 release 前会先清 dragging，
        # 接缝拖拽以本标志守卫
        self._strip_dragging = False
        self._strip_drag_x = 0
        self._strip_drag_w = 0
        # 抽屉滑入/滑出动画：QTimer 逐帧按缓动插值抽屉宽度，动画期暂挂抽屉与侧面板
        # 的宽度下限（允许滑过细缝），收口时按目标态重新落位
        self._drawer_timer = QTimer(self)
        self._drawer_timer.setInterval(16)
        self._drawer_timer.timeout.connect(self._tick_drawer_anim)
        self._drawer_dur = 200  # 动画时长（ms）
        self._drawer_elapsed = 0  # 已走时长（每 tick 固定累加 16ms）
        self._drawer_from = 0  # 本次动画起点宽
        self._drawer_target = 0  # 本次动画终点宽
        self._drawer_suspended = False  # 当前动画是否已暂挂下限（收口据此落位）
        self._drawer_shot = None  # 动画期换入的面板静态快照（None = 未快照）

        self.splitterMoved.connect(self._on_splitter_moved)
        self._side_panel.visibility_changed.connect(self._on_side_visibility)
        self._side_panel.min_width_changed.connect(self._on_side_min_changed)
        # 拉伸触发边 = 缩略列自身（发丝线接缝），拖拽信号换算抽屉宽
        self._thumbs.resize_started.connect(self._on_strip_resize_started)
        self._thumbs.resize_moved.connect(self._on_strip_resize_moved)
        self._thumbs.resize_finished.connect(self._on_strip_resize_finished)

    # 对外
    @property
    def side_panel(self) -> SidePanel:
        """侧面板（供 MainWindow 登记编辑窗口面板）"""
        return self._side_panel

    def drawer_handle(self):
        """抽屉拖拽手柄：返回缩略列（拉伸触发边 = 缩略列自身）"""
        return self._thumbs

    # 抽屉宽（三段换算）与拉伸触发边
    def _drawer_w(self) -> int:
        """当前抽屉区域宽 = 缩略列 + 面板（不含手柄，与目标/记忆宽同一口径）"""
        return self._thumbs.width() + self.widget(2).width()

    def _apply_drawer_w(self, drawer_w: int) -> None:
        """按抽屉区域宽落位三段：树 = 余量、缩略列 = 固定、面板 = 余下"""
        thumbs_w = self._thumbs.width()
        body_w = max(0, drawer_w - thumbs_w)
        tree_w = max(0, self.width() - thumbs_w - body_w)
        self.setSizes([tree_w, thumbs_w, body_w])

    # 接缝拖拽（缩略列自身 = 拉伸触发边）
    def _on_strip_resize_started(self, global_x: int) -> None:
        """接缝按下：记录拖拽基准（当前抽屉宽与光标全局 x）"""
        if not self._side_visible:
            return
        # 动画未收口时接缝已被按下：先停表收口，避免动画与拖拽 setSizes 互相覆盖
        if self._drawer_timer.isActive():
            self._drawer_timer.stop()
            self._finish_drawer()
        self._strip_dragging = True
        self._strip_drag_x = global_x
        self._strip_drag_w = self._drawer_w()
        self.dragging = True

    def _on_strip_resize_moved(self, global_x: int) -> None:
        """接缝拖动：按光标位移换算抽屉宽并落位（左拖增宽、右拖收窄）"""
        if not self._strip_dragging:
            return
        delta = self._strip_drag_x - global_x
        self._apply_drawer_w(max(0, self._strip_drag_w + delta))

    def _on_strip_resize_finished(self) -> None:
        """接缝松手：结束拖拽，按最终抽屉宽记忆面板展开宽度"""
        if not self._strip_dragging:
            return
        self._strip_dragging = False
        self.dragging = False
        if self._side_visible:
            thumbs_w = int(T("size.thumbs.w"))
            self._side_width = max(0, self._drawer_w() - thumbs_w)
            self._side_adjusted = True

    # 宽度联动
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # 主显示区总宽变化时刷新树/抽屉的比例拖拽界
        self._update_splitter_thirds()
        # 抽屉下限随总宽变化：非动画期直接落位，动画期由 _finish_drawer 收口时落位
        if not self._drawer_suspended:
            self._apply_drawer_floor()

    def _on_side_visibility(self, visible: bool) -> None:
        """抽屉显隐切换：滑入/滑出动画收口到目标宽（展开按黄金比例或用户记忆宽）"""
        self._side_visible = visible
        # 动画前不设抽屉下限：setMinimumWidth 会把抽屉立即推到下限宽导致动画跳档，
        # 下限由动画收口时 _finish_drawer 落位
        thumbs_w = int(T("size.thumbs.w")) if self._manager.windows else 0
        total = self.width()
        if visible and not self._side_adjusted and total > 0:
            # 黄金比例排布：抽屉 = 总宽 / (φ + 1)，树 = 总宽 × φ / (φ + 1)
            target = round(total / (self._PHI + 1))
        else:
            target = thumbs_w + (self._side_width if visible else 0)
        if visible:
            # 动画目标对齐落位宽：快照抓取宽 = 落位宽 = 内容所需宽，正文保持最终排版
            need = self._side_panel.minimum_content_width + thumbs_w
            target = max(target, need)
        self._animate_drawer_to(target)

    def _animate_drawer_to(self, target: int) -> None:
        """把抽屉宽度从当前值动画到目标宽（滑出/推回，QTimer 驱动 + 缓动）"""
        self._drawer_timer.stop()
        cur = self._drawer_w()
        self._drawer_from = cur
        self._drawer_target = target
        if abs(cur - target) < 2:
            self._finish_drawer()
            return
        # 暂挂抽屉与面板下限（否则 setSizes 被钳在下限宽、动画无法从细缝滑出），
        # 收口时按目标态重新落位；快照滑动对打开/收起都成立
        if self._drawer_shot is None:
            thumbs_w = int(T("size.thumbs.w"))
            self._prep_drawer_shot(max(cur, target) - thumbs_w)
        self.widget(2).setMinimumWidth(0)
        self._side_panel.setMinimumWidth(0)
        self._drawer_suspended = True
        self._drawer_elapsed = 0
        self._drawer_timer.start()

    def _prep_drawer_shot(self, grab_w: int) -> None:
        """把侧面板渲染成静态快照并换入抽屉布局，动画期以快照滑动（面板不重排）"""
        panel = self._side_panel
        panel.force_live_page()
        panel.setMaximumWidth(int(T("size.side_panel.w.max")))
        panel.setMinimumWidth(max(1, grab_w))
        panel.resize(max(1, grab_w), panel.height())
        panel.layout().activate()
        pm = panel.grab()
        panel.setMinimumWidth(0)
        if pm.isNull() or pm.width() <= 0:
            return
        self._drawer_shot = DrawerShot(pm)
        idx = self._drawer_lay.indexOf(panel)
        self._drawer_lay.insertWidget(idx, self._drawer_shot)
        self._drawer_lay.removeWidget(panel)
        panel.hide()

    def _restore_panel_live(self) -> None:
        """把快照换回实况侧面板（动画结束，面板恢复实时布局）"""
        idx = self._drawer_lay.indexOf(self._drawer_shot)
        self._drawer_lay.insertWidget(idx, self._side_panel)
        self._drawer_lay.removeWidget(self._drawer_shot)
        self._drawer_shot.deleteLater()
        self._drawer_shot = None
        self._side_panel.show()

    def _tick_drawer_anim(self) -> None:
        """每帧：按缓动插值抽屉宽度并落位；到达终点收口"""
        self._drawer_elapsed += self._drawer_timer.interval()
        t = min(1.0, self._drawer_elapsed / self._drawer_dur)
        if self._drawer_target >= self._drawer_from:
            ease = 1 - (1 - t) ** 3  # ease-out
        else:
            ease = (
                4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2
            )  # ease-in-out
        w = round(self._drawer_from + (self._drawer_target - self._drawer_from) * ease)
        self._apply_drawer_w(w)
        if t >= 1.0:
            self._drawer_timer.stop()
            self._finish_drawer()

    def _finish_drawer(self) -> None:
        """动画收口：按目标态落位宽度约束并把快照换回实况面板，精确 setSizes 到目标宽"""
        if self._drawer_suspended:
            self._drawer_suspended = False
        if self._drawer_shot is not None:
            self._restore_panel_live()
        # 抽屉 widget 下限按目标态重算：展开 = 黄金比例宽，收起 = 0
        self._apply_drawer_floor()
        # 侧面板下限按目标态重算：展开 = 内容所需最小宽，收起 = 0
        if self._side_visible:
            self._side_panel.refresh_min_width()
        else:
            self._side_panel.setMinimumWidth(0)
        # 面板宽度上界与目标态对齐：展开 = max_token，收起 = 压回 0
        self._side_panel.setMaximumWidth(
            int(T("size.side_panel.w.max")) if self._side_visible else 0
        )
        # 动画收口目标宽不能低于正文排布后的内容最小宽：开启动画的目标宽在面板首次
        # 真实宽度出现前估算，可能小于内容需求（打开带示例文件名的新模板等场景），
        # 若按旧目标收口，面板会比自身内容更宽，右缘（保存/关闭、卡片末区）被挤出
        # 可视区。这里以收口时重算的最小内容宽抬升目标，再精确落位。
        if self._side_visible:
            need = self._side_panel.minimum_content_width + self._thumbs.width()
            self._drawer_target = max(self._drawer_target, need)
        target = self._drawer_target
        self._apply_drawer_w(target)
        # 宽度动画收口时页面布局仍滞后一帧（窄宽幻影高度未收敛），通知侧面板
        # 在布局落定后补一轮正文滚动范围重算
        if self._side_visible:
            self._side_panel.notify_drawer_settled()

    def _apply_drawer_floor(self) -> None:
        """面板（widget 2）的拖拽下限：展开 = 黄金比例宽 − 缩略列，收起 = 0"""
        floor = round(self.width() / (self._PHI + 1)) if self._side_visible else 0
        body_floor = max(0, floor - self._thumbs.width())
        self.widget(2).setMinimumWidth(body_floor)

    def _on_side_min_changed(self, min_w: int) -> None:
        """面板内容最小宽增大时，若抽屉已窄于该值则加宽"""
        if not self._side_visible or self._drawer_timer.isActive():
            return
        thumbs_w = int(T("size.thumbs.w"))
        target = min_w + thumbs_w
        if self._drawer_w() < target:
            self._apply_drawer_w(target)

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        """拖拽调宽抽屉时记忆面板展开宽度；收起状态不更新"""
        if self._side_visible:
            thumbs_w = int(T("size.thumbs.w"))
            self._side_width = max(0, self._drawer_w() - thumbs_w)
            # 仅用户真正拖拽（dragging）才退出黄金比例默认排布
            if self.dragging:
                self._side_adjusted = True

    def _update_splitter_thirds(self) -> None:
        """把文件树与抽屉的拖拽界固定到主显示区的比例约束"""
        total = self.width()
        if total <= 0:
            return
        third = round(total / 3)
        self.widget(0).setMinimumWidth(max(third, int(T("size.tree.min.w"))))
