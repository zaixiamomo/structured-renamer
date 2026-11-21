"""模板分支：模板、默认加工和条件。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from sr.core.compile.condition import CompiledCondition, Condition
from sr.core.compile.template import CompiledTemplate, Template, TemplateUsage
from sr.core.compile.transform import CompiledTransform, Transform
from sr.core.contracts.compilable import Compilable
from sr.core.values import TokenValue

if TYPE_CHECKING:
    from sr.core.runtime.state import FileState


@dataclass(frozen=True, eq=False)
class CompiledTemplateBranch:
    """带加工和条件的分支编译产物。"""

    template: CompiledTemplate
    transform: CompiledTransform
    condition: CompiledCondition | None

    def match(
        self, text: str, *, file: FileState | None = None
    ) -> dict[str, TokenValue] | None:
        """先应用分支加工，再匹配模板并检查条件。

        Args:
            text: 待匹配的文本。
            file: 条件引用系统字段时使用的 FileState。
        Returns:
            捕获字段；模板不匹配或条件为假时返回 None。
        """
        text = self.transform.clean(text)
        captures = self.template.match(text)
        if captures is None:
            return None
        # 条件只看到字段的计算值，不携带 TokenValue。
        fields = {name: capture.value for name, capture in captures.items()}
        if self.condition is not None and not self.condition.evaluate(
            fields, file=file
        ):
            return None
        return captures


class TemplateBranch(BaseModel, Compilable[CompiledTemplateBranch]):
    """parse/render 列表中的单个分支声明。"""

    template: Template
    transform: Transform | None = None
    condition: Condition | None = None

    model_config = ConfigDict(frozen=True, extra="forbid")

    def compile(
        self,
        usage: TemplateUsage,
        default_transform: Transform | None = None,
    ) -> CompiledTemplateBranch:
        """编译模板、加工链和条件。

        Args:
            usage: parse 或 render。
            default_transform: 分支未声明 transform 时使用的默认加工。
        Returns:
            CompiledTemplateBranch。
        """
        transform = (
            self.transform
            if self.transform is not None
            else (default_transform or Transform(""))
        )
        return CompiledTemplateBranch(
            template=self.template.compile(usage),
            transform=transform.compile(),
            condition=self.condition.compile() if self.condition is not None else None,
        )
