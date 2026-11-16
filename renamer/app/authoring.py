"""制作面用例：模板和规则编辑所需的内省、编译校验与声明输出"""

from __future__ import annotations

from collections.abc import Mapping

from renamer.core import dsl
from renamer.core.codec import toml_codec
from renamer.core.compile import Plan, compile_rule
from renamer.core.compile.template import TemplateCompiler
from renamer.core.dsl import Call
from renamer.core.model import (
    Capability,
    Issue,
    Level,
    Library,
    ParseTemplate,
    PlanError,
    Rule,
    Template,
)
from renamer.core.plugins import DomainRegistry
from renamer.core.source import (
    SourceRule,
    SourceRuleToken,
    render_template_name,
)
from renamer.core.source.segment import SegmentedText, Span, segment

__all__ = [
    "AuthoringService",
    "Library",
    "ParseTemplate",
    "PlanError",
    "Rule",
    "SourceRuleToken",
    "Span",
    "Template",
    "compile_source_plan",
    "render_template_name",
]


def compile_source_plan(
    source: SourceRule, capabilities: Mapping[str, Capability]
) -> Plan:
    """将草稿导出为声明后编译执行计划，校验失败抛 PlanError"""
    library = source.to_library()
    return compile_rule(library.rules[source.name], library, capabilities)


class AuthoringService:
    """基于给定领域注册表提供编辑、查询和校验用例"""

    def __init__(self, registry: DomainRegistry) -> None:
        self._registry = registry

    # 词段（唯一 tokenizer）
    @staticmethod
    def tokenize(text: str, *, open: str = "{", close: str = "}") -> SegmentedText:
        """core.tokenize 的字符索引增强视图，唯一 tokenizer（委托 source.segment）"""
        return segment(text, open, close)

    # 校验（收口两套规则）
    def validate_template(self, template: Template) -> list[Issue]:
        """模板校验（core compile_parse 不抛错版本）"""
        try:
            TemplateCompiler.compile_parse(template)
        except PlanError as exc:
            return exc.issues
        return []

    def validate_rule(
        self,
        rule: Rule,
        library: Library,
        capabilities: dict[str, Capability] | None = None,
    ) -> list[Issue]:
        """校验规则并返回诊断，未指定能力时使用当前服务的领域注册表"""
        if capabilities is None:
            capabilities = self._registry.capabilities_by_id()
        try:
            compile_rule(rule, library, capabilities)
        except PlanError as exc:
            return exc.issues
        return []

    @staticmethod
    def restore_rule(rule: Rule, library: Library) -> SourceRule:
        """从持久声明恢复可编辑草稿，不运行能力或要求示例文件。"""
        return SourceRule.from_rule(rule, library)

    # 内省
    def list_capabilities(self, implemented_only: bool = False) -> list[Capability]:
        return self._registry.list_capabilities(implemented_only=implemented_only)

    def field_types(self) -> dict[str, str]:
        """把注册字段投影为编辑器使用的名称和类型文本"""
        return {
            str(key): field.type.value
            for key, field in self._registry.fields_by_key().items()
        }

    def preview_parse(self, filename: str, template_name: str) -> dict[str, str]:
        """按命名解析模板反向解析字符串，返回 token 到捕获值的映射

        Args:
            filename: 待解析的字符串（通常为文件名 stem）
            template_name: 注册的解析模板名

        Returns:
            token 名到捕获值的映射，不匹配时为空 dict

        Raises:
            PlanError: 模板名未注册或模板编译失败
        """
        template = self._registry.find_parse_template(template_name)
        if template is None:
            raise PlanError(
                [
                    Issue(
                        level=Level.ERROR,
                        code="template_not_found",
                        message=f"解析模板 {template_name!r} 未注册",
                    )
                ]
            )
        compiled = TemplateCompiler.compile_parse(template)
        return compiled.parse(filename) or {}

    @staticmethod
    def infer_type(text: str) -> str:
        """按示例文本推断类型（纯数字为 int、日期形为 date，否则 string）"""
        return dsl.infer_type(text)

    @staticmethod
    def int_content_conflict(type_str: str | None, value: str, name: str) -> str | None:
        """int 词段内容非整数，作者侧对示例值的补充校验"""
        if type_str == "int" and not value.isdigit():
            return f"词段 {name} 不是整数"
        return None

    # 渲染格式（render 函数族词表/校验/求值，唯一入口 core.dsl.format）
    @staticmethod
    def parse_format(spec: str) -> tuple[Call, ...]:
        """编辑器读取格式链，复用核心引号、参数和管道文法。"""
        return dsl.parse_expr(spec)

    @staticmethod
    def format_expression(calls: tuple[Call, ...]) -> str:
        """格式链编辑结果统一序列化。"""
        return dsl.fmt_expr(calls)

    @staticmethod
    def format_call(name: str, args: tuple[str, ...] = ()) -> str:
        """将单步编辑值编码为格式表达式，参数引号与转义由核心处理。"""
        return dsl.fmt_expr((Call(name, args),))

    @staticmethod
    def format_reference(
        name: str, spec: str = "", *, open: str = "{", close: str = "}"
    ) -> str:
        """编辑器新增引用时使用核心转义和注解打印规则。"""
        annotation = dsl.parse_expr(spec) if spec else None
        return dsl.fmt_draft_placeholder(name, annotation, open, close)

    @staticmethod
    def list_formats() -> list[dict]:
        """内置格式函数族内省元数据（GUI 格式编辑器下拉）"""
        return dsl.list_formats()

    @staticmethod
    def validate_format(spec: str) -> list[str]:
        """渲染格式链校验（词法/未知函数/参数个数/形态），空=合法"""
        return dsl.validate_expr(spec)

    @staticmethod
    def format_value(value: str, spec: str) -> str:
        """按渲染格式链对单个值求值；非法链按原值透传"""
        if not spec or spec == "string":
            return value
        try:
            calls = dsl.parse_expr(spec)
        except ValueError:
            return value
        return dsl.apply_chain(value, calls)

    # 声明输出
    def emit_library(self, library: Library) -> str:
        return toml_codec.emit(library)
