"""模板模型：ParseTemplate / RenderTemplate（出生即定型的两个方向角色）

解析与渲染虽共享同一词法（``{name:...}`` 占位与分隔符），但语义分向：

- ``ParseTemplate``：冒号后是捕获类型（string/int/date/enum），只用于反向匹配；
- ``RenderTemplate``：冒号后是格式表达式（render 函数族链），只用于正向输出。

同一段文字在类型层只能归属一个角色，规则引用时按角色查对应命名空间，
杜绝"同一模板身兼两职"的心智混叠。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

DEFAULT_DELIM_OPEN = "{"
DEFAULT_DELIM_CLOSE = "}"


class Template(BaseModel):
    text: str
    open: str = DEFAULT_DELIM_OPEN
    close: str = DEFAULT_DELIM_CLOSE

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def _check_delimiters(self) -> Template:
        if not self.open:
            raise ValueError("open 不能为空")
        if not self.close:
            raise ValueError("close 不能为空")
        if self.open == self.close:
            raise ValueError("open 与 close 不能相同")
        return self


class ParseTemplate(Template):
    """解析模板：只捕获，冒号后为捕获类型"""

    kind: Literal["parse"] = "parse"


class RenderTemplate(Template):
    """渲染模板：只输出，冒号后为格式表达式"""

    kind: Literal["render"] = "render"
