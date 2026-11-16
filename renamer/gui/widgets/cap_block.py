"""单个能力块：选能力后固定在此，新块在上、旧块在下"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from renamer.app.rule_editing import CapabilityValues
from renamer.core.model import Capability

from .cap_slot import CapSlot
from .flow_layout import FlowLayout
from .remove_button import RemoveButton

__all__ = ["CapBlock", "capability_display_name"]


def capability_display_name(cap: Capability) -> str:
    """下拉与能力块共用的领域优先显示名；保留原始能力 ID。"""
    parts = cap.id.split(".", 2)
    if len(parts) == 3 and all(parts) and parts[0] == cap.channel.value:
        channel, domain, name = parts
        return f"{domain}.{channel}.{name}"
    return cap.id


class CapBlock(QFrame):
    """单个能力块"""

    token_dropped = Signal(str, int)  # (field_key, tid) 上报面板
    unbind_requested = Signal(str)  # field_key 上报面板
    run_requested = Signal(object)  # 携带本块 cap 上报面板（点击「运行」）
    output_activate = Signal(str)
    output_deactivate = Signal(str)
    remove_requested = Signal(object)  # 携带本块上报面板

    def __init__(self, cap, parent=None):
        super().__init__(parent)
        self._cap = cap
        self.setProperty("role", "cap-block")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        lay = QVBoxLayout(self)
        # 左右归 0 与分区内容同列对齐；上下等距 8，块间由块顶细线分隔
        lay.setContentsMargins(0, 8, 0, 8)
        lay.setSpacing(6)

        # 头部：能力名 + 移除
        head = QWidget()
        hl = QHBoxLayout(head)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)
        title = QLabel(capability_display_name(cap))
        title.setProperty("role", "cap-title")
        title.setWordWrap(True)
        hl.addWidget(title, 1)
        self._run_btn = QPushButton("运行")
        self._run_btn.setProperty("role", "d-btn-primary")
        self._run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._emit_run)
        self._run_state = "idle"
        self._ready = False
        hl.addWidget(self._run_btn)
        rm = RemoveButton("移除能力")
        rm.clicked.connect(self._emit_remove)
        hl.addWidget(rm)
        lay.addWidget(head)

        self._in_slots: dict[str, CapSlot] = {}
        self._out_slots: dict[str, CapSlot] = {}
        if cap.inputs:
            in_cap = QLabel("输入 · 拖入词段绑定")
            in_cap.setProperty("role", "slot-cap")
            lay.addWidget(in_cap)
        self._in_flow = FlowLayout(margin=0, spacing=6)
        for field in cap.inputs:
            slot = CapSlot(str(field), drops=True)
            slot.token_dropped.connect(self.token_dropped)
            slot.unbind_requested.connect(self.unbind_requested)
            self._in_flow.addWidget(slot)
            self._in_slots[str(field)] = slot
        lay.addLayout(self._in_flow)

        if cap.outputs:
            out_cap = QLabel("输出 · 点击选用，运行可预览")
            out_cap.setProperty("role", "slot-cap")
            lay.addWidget(out_cap)
        self._out_flow = FlowLayout(margin=0, spacing=6)
        for field in cap.outputs:
            slot = CapSlot(str(field), drops=False)
            slot.output_activate.connect(self.output_activate)
            slot.output_deactivate.connect(self.output_deactivate)
            self._out_flow.addWidget(slot)
            self._out_slots[str(field)] = slot
        lay.addLayout(self._out_flow)

    @property
    def cap(self):
        return self._cap

    def _emit_remove(self) -> None:
        self.remove_requested.emit(self)

    def set_run_display(self, state: str, seconds: int, completed: bool) -> None:
        """仅呈现任务协调者的运行状态，不维护计时或取消策略"""
        self._run_state = state
        self._apply_run_prop("" if state == "idle" else state)
        if state == "running":
            self._run_btn.setText(f"运行 {seconds}s")
            self._run_btn.setToolTip("运行中 · 点击中断")
        elif state == "interrupted":
            self._run_btn.setText("已中断")
            self._run_btn.setToolTip("已中断 · 点击重新运行")
        else:
            self._run_btn.setText("运行")
            self._run_btn.setToolTip(
                "运行完成，可再次运行覆盖结果" if completed else ""
            )
        self._run_btn.setEnabled(state in ("running", "interrupted") or self._ready)

    def _apply_run_prop(self, value: str) -> None:
        self._run_btn.setProperty("runstate", value)
        self._run_btn.style().unpolish(self._run_btn)
        self._run_btn.style().polish(self._run_btn)

    def _emit_run(self) -> None:
        self.run_requested.emit(self._cap)

    def refresh(self, values: CapabilityValues, active_tokens: set[int]) -> None:
        """完整刷新槽位，页面无需了解内部控件"""
        for field, slot in self._in_slots.items():
            if field in values.inputs:
                value, unbind = values.inputs[field]
                slot.set_bound(value, unbind=unbind)
            else:
                slot.set_idle()
        for field, slot in self._out_slots.items():
            if field in values.outputs:
                tid, name, value = values.outputs[field]
                slot.set_done(value, active=tid in active_tokens, name=name)
            else:
                slot.set_idle()
        self._ready = values.ready
        self._run_btn.setEnabled(self._run_state == "running" or self._ready)
