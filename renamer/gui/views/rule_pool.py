"""规则词池：词段展示；占位与底部冻结交给共用滚动分区。"""

from collections.abc import Iterable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from ..widgets.flow_layout import FlowLayout
from ..widgets.frozen_section import FrozenSection
from ..widgets.token_chip import TokenChip


class FloatingTokenPool(FrozenSection):
    token_deactivated = Signal(int)

    def __init__(self, owner: QWidget, holder: QWidget, panes: list[QWidget]):
        super().__init__(owner, holder, panes, edge="bottom")
        self.flow = FlowLayout(margin=0, spacing=6)
        self.body.addLayout(self.flow)

    @property
    def has_tokens(self) -> bool:
        return self.flow.count() > 0

    def set_chips(self, chips: Iterable[TokenChip]) -> None:
        while self.flow.count():
            widget = self.flow.takeAt(0).widget()
            widget.setParent(None)
            widget.deleteLater()
        for chip in chips:
            chip.right_clicked.connect(self.token_deactivated)
            self.flow.addWidget(chip)
        self.set_enabled(self.has_tokens)
