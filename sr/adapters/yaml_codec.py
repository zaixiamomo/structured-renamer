"""YAML 规则编解码。"""

import yaml
from pydantic import BaseModel, ConfigDict, Field
from yaml.composer import ComposerError
from yaml.constructor import ConstructorError
from yaml.events import AliasEvent

from sr.app.protocols import RuleCodec
from sr.core.compile.rule import Rule
from sr.core.compile.template import (
    DEFAULT_TEMPLATE_DELIMITER_CLOSE,
    DEFAULT_TEMPLATE_DELIMITER_OPEN,
    Template,
)
from sr.core.compile.template_branch import TemplateBranch
from sr.core.compile.token import Token


class _Loader(yaml.SafeLoader):
    """禁止 YAML 锚点、别名、显式标签和重复键的加载器。"""

    def compose_node(self, parent, index):
        """拒绝可能造成展开或注入的 YAML 节点特性。

        Args:
            parent: PyYAML 提供的父节点。
            index: 节点在父容器中的位置。
        Returns:
            由 SafeLoader 构造的节点。
        Raises:
            ComposerError: 节点使用锚点、别名或显式标签。
        """
        event = self.peek_event()
        if (
            isinstance(event, AliasEvent)
            or getattr(event, "anchor", None) is not None
            or getattr(event, "tag", None) is not None
        ):
            raise ComposerError(
                None, None, "不支持锚点、别名或显式标签", event.start_mark
            )
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):
        """要求映射键为唯一字符串。

        Args:
            node: 待构造的 YAML 映射节点。
            deep: 是否立即构造嵌套对象。
        Returns:
            由 SafeLoader 构造的映射。
        Raises:
            ConstructorError: 键不是字符串、使用合并键或出现重复键。
        """
        keys: set[str] = set()
        for key_node, _ in node.value:
            if key_node.tag != "tag:yaml.org,2002:str":
                raise ConstructorError(
                    None, None, "映射键必须是字符串，不支持合并键", key_node.start_mark
                )
            key = key_node.value
            if key in keys:
                raise ConstructorError(
                    None, None, f"重复键：{key}", key_node.start_mark
                )
            keys.add(key)
        return super().construct_mapping(node, deep=deep)


class _Declaration(BaseModel):
    """所有 YAML 声明模型的基类。"""

    model_config = ConfigDict(extra="forbid")


class _Branch(_Declaration):
    """YAML 中的模板分支声明。"""

    template: str | Template
    transform: str | None = None
    condition: str | None = None


class _Transform(_Declaration):
    """YAML 中的默认加工链声明。"""

    parse: str | None = None
    render: str | None = None


class _Group(_Declaration):
    """YAML 中的分组声明。"""

    token: str
    partition: str = "equal"


class _Extension(_Declaration):
    """YAML 中的拓展声明。"""

    name: str
    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str]
    options: dict[str, object] = Field(default_factory=dict)


class _Document(_Declaration):
    """YAML 规则文档。"""

    name: str
    transform: _Transform | None = None
    parse: tuple[_Branch, ...]
    render: tuple[_Branch, ...]
    group: tuple[_Group, ...] | None = None
    extensions: tuple[_Extension, ...] = ()


class YamlCodec(RuleCodec):
    """在 Rule 与 YAML 文本之间转换。"""

    def decode(self, text: str) -> Rule:
        """解析 YAML 规则文本。

        Args:
            text: 完整 YAML 文档。
        Returns:
            校验后的 Rule。
        Raises:
            TypeError: 输入不是 str。
            yaml.YAMLError: YAML 语法或受限特性错误。
            pydantic.ValidationError: 声明结构不合法。
        """
        if not isinstance(text, str):
            raise TypeError("YAML 输入必须是 str")
        document = _Document.model_validate(yaml.load(text, Loader=_Loader))
        # 先把简写字符串规范为 Rule 所需的模型字典。
        data = document.model_dump()
        if data["transform"] is not None:
            data["transform"] = {
                key: {"text": value}
                for key, value in data["transform"].items()
                if value is not None
            }
        for usage in ("parse", "render"):
            for branch in data[usage]:
                if isinstance(branch["template"], str):
                    branch["template"] = {"text": branch["template"]}
                if branch["transform"] is not None:
                    branch["transform"] = {"text": branch["transform"]}
                if branch["condition"] is not None:
                    branch["condition"] = {"text": branch["condition"]}
        return Rule.model_validate(data)

    def encode(self, value: Rule) -> str:
        """把 Rule 序列化为 YAML 文本。

        Args:
            value: 待编码规则。
        Returns:
            使用块样式、保留 Unicode 的 YAML 文档。
        Raises:
            TypeError: 输入不是 Rule。
        """
        if not isinstance(value, Rule):
            raise TypeError("YAML 编码对象必须是 Rule")
        data: dict[str, object] = {"name": value.name}
        if value.transform:
            parse = value.transform.get("parse")
            render = value.transform.get("render")
            transform = {}
            if parse is not None and parse.text != "":
                transform["parse"] = parse.text
            if render is not None and render.text != "":
                transform["render"] = render.text
            if transform:
                data["transform"] = transform
        # 省略默认值，保持往返编码的最小输出。
        data["parse"] = [_encode_branch(branch) for branch in value.parse]
        data["render"] = [_encode_branch(branch) for branch in value.render]
        if value.group:
            data["group"] = [
                {
                    "token": _encode_token(entry.token),
                    **(
                        {"partition": entry.partition.text}
                        if entry.partition.text != "equal"
                        else {}
                    ),
                }
                for entry in value.group
            ]
        if value.extensions:
            data["extensions"] = [
                {
                    "name": extension.name,
                    **({"options": extension.options} if extension.options else {}),
                    "inputs": {
                        port: _encode_token(token)
                        for port, token in extension.inputs.items()
                    },
                    "outputs": {
                        port: _encode_token(token)
                        for port, token in extension.outputs.items()
                    },
                }
                for extension in value.extensions
            ]
        return yaml.safe_dump(
            data,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=2**31 - 1,
        )


def _encode_branch(branch: TemplateBranch) -> dict[str, object]:
    """把分支压缩为 YAML 可读的简写形式。"""
    template = branch.template
    if (
        template.open == DEFAULT_TEMPLATE_DELIMITER_OPEN
        and template.close == DEFAULT_TEMPLATE_DELIMITER_CLOSE
    ):
        data: dict[str, object] = {"template": template.text}
    else:
        data = {"template": template.model_dump(exclude_defaults=True)}
    if branch.transform is not None:
        data["transform"] = branch.transform.text
    if branch.condition is not None:
        data["condition"] = branch.condition.text
    return data


def _encode_token(token: Token) -> str:
    """把词段还原为 name[=qualifier][:transform] 表达式。"""
    expression = token.name
    if token.qualifier is not None:
        expression += "=" + token.qualifier
    if token.transform.text != "":
        expression += ":" + token.transform.text
    return expression
