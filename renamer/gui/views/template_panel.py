"""模板面板：测试文本划词拆分、词流编辑、模板 TOML 单向下发只读展示"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)

from renamer.app.authoring import (
    AuthoringService,
    ParseTemplate,
)
from renamer.app.template_editing import TemplateEditor

from ..state.window import Window
from ..toml_projection import toml_lines, toml_string
from ..widgets.editor_card import EditorCard
from ..widgets.status_label import StatusLabel
from ..widgets.template_token_row import TemplateTokenRow
from ..widgets.toml_edit import TomlEdit
from ..widgets.word_canvas import WordCanvas
from .panel_base import EditorPanel

__all__ = ["TemplatePanel"]

# 空白模板占位名（WindowManager.open 的默认名），进入面板视为空内容
_PLACEHOLDER = "（新建模板）"


class TemplatePanel(EditorPanel):
    """编辑模板窗口面板：划词拆分、词流编辑、模板 TOML 只读展示"""

    def __init__(
        self,
        win: Window,
        *,
        manager,
        session,
        authoring: AuthoringService,
        parent=None,
    ):
        super().__init__(parent)
        self._win = win
        self._manager = manager
        self._session = session
        self._authoring = authoring
        self._editor = TemplateEditor(
            authoring, session.authoring_session, self._default_template_name()
        )
        self._conflicts: dict[int, str] = {}
        self._rows: dict[int, TemplateTokenRow] = {}
        self._build()
        self._manager.register_name(self._win.id, self._editor.name)
        self.set_filename(win.filename)
        # 拖放目标：模板页铺满抽屉主视图区，文件树的文件拖入整区任意位置即替换
        # 示例文件名，不做分区高亮（_build 里把会吞拖放的输入控件 acceptDrops
        # 关掉，放置事件统一收口到本页）
        self.setAcceptDrops(True)

    # 对外契约
    def set_filename(self, text: str) -> None:
        """新建模板按示例划词；已载入模板只更新可选匹配投影。"""
        if text == _PLACEHOLDER:
            text = ""
        message = self._editor.set_sample(text)
        self._canvas.clear_selection()
        self._sync_all()
        if message:
            self._warn_checkbar(message)

    def _default_template_name(self) -> str:
        return self._manager.available_name(
            "user_template", self._session.templates, self._win.id
        )

    def save(self) -> bool:
        """登记模板到会话存储；校验通过返回 True（侧面板据此关闭窗口）"""
        issue = self._editor.save()
        if issue is not None:
            guidance = {
                "template_name_required": "（顶栏名称编辑框填写）",
                "template_text_required": "，先在示例文件名中划词",
            }
            self._warn_checkbar(issue.message + guidance.get(issue.code, ""))
            return False
        return True

    def load_template(self, name: str, template: ParseTemplate) -> None:
        """恢复权威草稿；没有示例时仍可改名、编辑词段并原样保存。"""
        self._editor.load(name, template)
        self._manager.register_name(self._win.id, name)
        self._canvas.clear_selection()
        self._sync_all()

    # 顶栏名称编辑（侧面板标题框到模板名）
    @property
    def name(self) -> str:
        """当前模板名（顶栏名称编辑的读口）"""
        return self._editor.name

    def set_name(self, text: str) -> None:
        """顶栏重命名模板，更新模板名并刷新 TOML（占用登记同步更新）"""
        text = text.strip()
        if not text or text == self._editor.name:
            return
        self._editor.name = text
        self._manager.register_name(self._win.id, text)
        self._set_template_toml()
        self.name_changed.emit()

    # 三区同步引擎
    def _sync_all(self, *, rebuild_rows: bool = True) -> None:
        """更新草稿投影；行内编辑只刷新校验和预览，保留输入焦点。"""
        # 无文件时提示拖入，有文件时给划词操作引导
        self._conflicts = self._editor.token_conflicts()
        self._canvas.set_content(
            self._editor.source.chars,
            self._editor.source.token_of(),
            self._editor.source.tokens,
        )
        self._refresh_hint()
        if rebuild_rows:
            self._rebuild_flow()
        self._set_template_toml()
        self._update_checkbar()

    def _refresh_hint(self) -> None:
        """拆分卡提示态：空文档（无示例文本）时收起画布为单行居中提示

        与卡片2 空态同构（隐藏容器 + 预留同一行高的提示行），保证两张
        卡片初始状态等高、提示文字不被画布空行挤到底部；有文本时画布接管，
        提示恢复普通 note 随文本换行。
        """
        empty = not self._editor.source.has_sample or not self._editor.source.chars
        self._canvas.setVisible(not empty)
        if empty:
            self._hint.setText(
                "模板已载入，可直接编辑词段；拖入匹配的示例文件可预览"
                if self._editor.source.is_loaded
                else self._hint_prompt
            )
            self._hint.setMinimumHeight(EditorCard.HINT_ROW_HEIGHT)
        else:
            self._hint.setText(self._hint_default)
            self._hint.setMinimumHeight(0)
        self._hint.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

    def _set_template_toml(self) -> None:
        """按词流生成真实 TOML 写入末卡（只读展示）"""
        self._display_toml(self._editor.toml_text())

    def _display_toml(self, text: str) -> None:
        """写入末卡文本并登记 name/token 高亮与点击跳转区间（剥尾空行去重由
        TomlEdit.set_content 收口，与规则面板末卡同套路）"""
        self._toml_edit.set_content(text, self._click_regions(text))

    def _click_regions(self, text: str) -> list[dict]:
        """定位末卡可点击区间：name 值 + text 内 token 占位（明文坐标，end 不含）

        token 与词流按顺序一一对应；词段数量对不上（如重开只载 TOML、text 含
        字面 ``{...}``）时不标 token 区间，避免点击跳到错误词段。
        """
        toks = self._editor.source.ordered_tokens()
        regions: list[dict] = []
        for line, offset in toml_lines(text):
            name = toml_string(line, offset, "name")
            if name is not None:
                regions.append(name.name_region())
            else:
                value = toml_string(line, offset, "text")
                if value is None:
                    continue
                parsed = [
                    s
                    for s in self._authoring.tokenize(
                        value.decoded,
                        open=self._editor.source.open,
                        close=self._editor.source.close,
                    ).spans
                    if s.is_token()
                ]
                if len(parsed) != len(toks):
                    continue
                for sp, (tid, _doc_sp) in zip(parsed, toks):
                    regions.append(value.token_region(tid, sp.s, sp.e))
        return regions

    def _update_checkbar(self) -> None:
        """匹配区底部提示三态：无词段居中提示、正常隐藏、有冲突报错"""
        if not self._editor.source.tokens:
            self._checkbar.setText("无匹配词段")
            self._checkbar.set_status("")
            # flow_host 空态已隐藏（间距不占位）；预留一行高使卡片高度与首个
            # 词段出现时一致，文字在预留空间内上下居中、左对齐
            self._checkbar.setMinimumHeight(EditorCard.HINT_ROW_HEIGHT)
            self._checkbar.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            self._checkbar.setVisible(True)
            return
        reasons = sorted(set(self._conflicts.values()))
        if reasons:
            self._warn_checkbar("；".join(reasons))
            return
        self._checkbar.setVisible(False)

    def _warn_checkbar(self, text: str) -> None:
        """错误提示：note 样式左对齐 + 警告色文字（区别于空态提示）"""
        self._checkbar.setText(text)
        self._checkbar.set_status("warn")
        self._checkbar.setMinimumHeight(0)
        self._checkbar.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._checkbar.setVisible(True)

    # 事件（画布到面板）
    def _on_confirm(self, s: int, e: int) -> None:
        """右键确认选区，生成词段并全量同步（重叠/越界交给 SourceTemplate.mark 判定）"""
        try:
            self._editor.mark(s, e)
        except ValueError:
            self._canvas.clear_selection()
            return
        self._canvas.clear_selection()
        self._sync_all()

    def _on_unconfirm(self, tid: int) -> None:
        """右键已标词段或点删除，撤销该词段并全量同步"""
        self._editor.unmark(tid)
        self._sync_all()

    def _on_token_clicked(self, tid: int) -> None:
        """画布/末卡 TOML 左键点击词段，词流对应名称输入获得焦点并全选"""
        row = self._rows.get(tid)
        if row is not None:
            row.focus_name()

    def _on_sel_changed(self, s: int, e: int) -> None:
        self._hint.setText(f"已选 {e - s + 1} 个字符")

    # 事件（词流内编辑，避免整建丢焦点）
    def _on_name_edited(self, tid: int, text: str) -> None:
        if tid not in self._editor.source.tokens:
            return
        self._editor.rename_token(tid, text)
        self._sync_all(rebuild_rows=False)

    def _on_type_changed(self, tid: int, type_name: str) -> None:
        if tid not in self._editor.source.tokens:
            return
        self._editor.set_token_type(tid, type_name)
        self._rows[tid].set_candidates(self._editor.candidate_text(tid))
        self._sync_all(rebuild_rows=False)

    def _on_values_edited(self, tid: int, text: str) -> None:
        if tid not in self._editor.source.tokens:
            return
        self._editor.set_candidate_text(tid, text)
        self._sync_all(rebuild_rows=False)

    def _rebuild_flow(self) -> None:
        for row in self._rows.values():
            self._flow_lay.removeWidget(row)
            row.deleteLater()
        self._rows.clear()
        tokens = self._editor.source.ordered_tokens()
        self._flow_host.setVisible(bool(tokens))
        for index, (tid, spec) in enumerate(tokens, 1):
            row = TemplateTokenRow(
                index,
                name=spec.name or "",
                type_name=spec.type or "string",
                sample=self._editor.source.sample_text(tid),
                candidates=self._editor.candidate_text(tid),
            )
            row.name_edited.connect(
                lambda text, tid=tid: self._on_name_edited(tid, text)
            )
            row.type_changed.connect(
                lambda type_name, tid=tid: self._on_type_changed(tid, type_name)
            )
            row.candidates_edited.connect(
                lambda text, tid=tid: self._on_values_edited(tid, text)
            )
            row.remove_requested.connect(lambda tid=tid: self._on_unconfirm(tid))
            self._flow_lay.addWidget(row)
            self._rows[tid] = row
        self.content_changed.emit()

    # 构造
    def _build(self) -> None:
        lay = self._make_layout()

        # 1) 测试文本
        pane1 = EditorCard()
        p1 = pane1.body
        self._canvas = WordCanvas()
        self._canvas.selection_confirmed.connect(self._on_confirm)
        self._canvas.token_unconfirmed.connect(self._on_unconfirm)
        self._canvas.token_clicked.connect(self._on_token_clicked)
        self._canvas.selection_changed.connect(self._on_sel_changed)
        p1.addWidget(self._canvas)
        self._hint_default = "左键拖选 · 右键确认"
        self._hint_prompt = "从文件树拖入文件，开始划词拆分"
        self._hint = QLabel(self._hint_prompt)
        self._hint.setProperty("role", "note")
        self._hint.setWordWrap(True)
        p1.addWidget(self._hint)
        lay.addWidget(self._pane_cap("1. 拆分"))
        lay.addWidget(pane1)

        # 2) 匹配
        pane2 = EditorCard()
        p2 = pane2.body
        flow_title = self._pane_cap("2. 匹配")
        self._flow_host = QWidget()
        self._flow_lay = QVBoxLayout(self._flow_host)
        self._flow_lay.setContentsMargins(0, 0, 0, 0)
        self._flow_lay.setSpacing(6)
        p2.addWidget(self._flow_host)
        self._checkbar = StatusLabel("无匹配词段")
        self._checkbar.setProperty("role", "note")
        self._checkbar.setWordWrap(True)
        p2.addWidget(self._checkbar)
        lay.addWidget(flow_title)
        lay.addWidget(pane2)

        # 3) 模板 TOML（真实 [[template]] 块，只读展示；结构化编辑是唯一入口）
        pane3 = EditorCard()
        p3 = pane3.body
        self._toml_edit = TomlEdit.readonly()
        # name/token 高亮区左键跳转：与卡片1 词段点击同一套定位逻辑
        self._toml_edit.name_clicked.connect(self.name_edit_requested.emit)
        self._toml_edit.token_clicked.connect(self._on_token_clicked)
        p3.addWidget(self._toml_edit)
        lay.addWidget(self._pane_cap("3. 模板"))
        lay.addWidget(pane3)

        lay.addStretch(1)
