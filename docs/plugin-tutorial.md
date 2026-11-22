# 插件编写教程

> Python 3.10+ · uv · Windows

主程序把插件当作独立的 Python 包。插件通过 `sr.plugins` 入口提供一个 `Domain`，规则用 `领域:能力` 调用其中的 `Extender`。本文从零完成一个最小插件，再说明系统字段、宿主资源和调试方法。

本文对应主程序 0.2.x。插件不需要修改主程序源码。

## 1. 目录结构

```text
sr-plugin-example/
├── pyproject.toml
├── extenders/
│   ├── __init__.py
│   └── prefix_title.py
└── demo/
    ├── rule.yaml
    └── examples/
        └── Sample A.txt
```

`extenders/` 是插件包，`demo/` 用于调试。`demo/examples/Sample A.txt` 可以是空文件。

示例沿用参考插件的 `extenders` 包名。如果要同时安装多个插件，每个插件应使用不同的 Python 包名，并同步修改入口点和构建路径，否则会互相覆盖。

## 2. 搭建开发环境

在插件仓库根目录创建虚拟环境，并先把主程序按可编辑方式装进去：

```powershell
uv venv
uv pip install --python .venv\Scripts\python.exe -e "D:\path\to\structured-renamer"
```

把 `D:\path\to\structured-renamer` 换成实际主项目路径。如果默认 Python 低于 3.10，改用 `uv venv --python 3.12` 创建环境。

插件的包和入口点还没创建，先不安装插件；完成第 3-5 节后，在第 6 节安装。

## 3. 编写能力

`extenders/prefix_title.py`：

```python
from collections.abc import Mapping

from sr.core.contracts.extender import Extender
from sr.core.values import SystemValue, TokenValue


class PrefixTitle(Extender):
    name = "prefix_title"
    input_ports = ("title",)
    output_ports = ("title",)

    def extend(
        self,
        input_values: Mapping[str, TokenValue],
        system_values: Mapping[str, SystemValue],
        *,
        options: Mapping[str, object],
    ) -> Mapping[str, TokenValue]:
        prefix = options.get("prefix", "Archive_")
        if not isinstance(prefix, str):
            raise ValueError("prefix 必须是文本")
        result = prefix + input_values["title"].value
        return {"title": TokenValue(value=result, raw=result, operations=())}
```

`Extender` 的声明和作用：

| 成员 | 作用 |
| --- | --- |
| `name` | 能力短名称，规则中写作 `领域:能力` |
| `input_ports` | 输入端口元组，规则必须全部绑定 |
| `output_ports` | 输出端口元组，规则按需绑定 |
| `system_bindings` | 端口到 `SystemField` 的映射，见第 8 节 |
| `required_resources` | 需要的宿主资源，只支持 `http` 和 `media` |
| `create` | 创建批次实例；需要资源时重写 |
| `supports` | 判断能力是否适用于当前文件 |
| `extend` | 处理输入并返回输出字段 |

端口名必须唯一且非空。

`extend` 返回“输出端口名到 `TokenValue`”的映射。`value` 和 `raw` 都是文本；数字、日期等先转成字符串。`operations=()` 表示不附带额外加工链。至少要返回规则绑定的输出端口，通常直接返回全部声明端口。

同一个能力实例可能被不同组并发调用。把当前输入、配置和结果放在局部变量中，不要写入实例属性。

## 4. 注册领域

`extenders/__init__.py`：

```python
from sr.plugin import Domain

from .prefix_title import PrefixTitle

__version__ = "0.1.0"

DOMAIN = Domain(name="example", extenders=(PrefixTitle,))
```

- `Domain.name` 是领域名，`PrefixTitle.name` 是能力名，规则中写 `example:prefix_title`。
- 一个领域可以登记多个能力类。
- 领域名和能力名都不能包含冒号；同名领域或同名能力会在启动时报错。

## 5. 声明入口点

`pyproject.toml`：

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "sr-plugin-example"
dynamic = ["version"]
requires-python = ">=3.10"
dependencies = ["structured-renamer>=0.2.0,<0.3.0"]

[project.entry-points."sr.plugins"]
example = "extenders:DOMAIN"

[tool.hatch.build.targets.wheel]
packages = ["extenders"]

[tool.hatch.version]
path = "extenders/__init__.py"
```

- `[project.entry-points."sr.plugins"]` 是主程序发现插件的入口组。
- `example = "extenders:DOMAIN"` 表示导入 `extenders` 包并读取 `DOMAIN`。入口名通常与领域名一致，`DOMAIN` 必须是 `Domain` 实例。
- `dependencies` 声明宿主版本范围；本文对应主程序 0.2.x。版本范围不匹配时，安装或运行会失败。
- 插件和主程序在同一个进程中运行，依赖版本必须兼容。
- 版本号从 `extenders/__init__.py` 的 `__version__` 读取。
- 只写一个 Python 文件、没有安装和入口点，主程序不会发现它。

## 6. 安装插件并验证

插件包和入口点已经就绪，把插件也装进同一个环境：

```powershell
uv pip install --python .venv\Scripts\python.exe -e .
```

主程序已在第 2 节安装。运行时使用这个环境里的 `sr.exe`，不要用全局的 `sr`。

检查入口点：

```powershell
.\.venv\Scripts\python.exe -c "from importlib.metadata import entry_points; print([(e.name, e.value) for e in entry_points(group='sr.plugins')])"
```

应看到（至少包含）：

```text
[('example', 'extenders:DOMAIN')]
```

- 修改 Python 代码后直接重新运行，不需要重装。
- 修改入口点、包名或依赖后，重新执行 `uv pip install`。
- 插件需要额外依赖时，加到插件自己的 `dependencies`，不要改主程序。
- 不要用 `uv sync` 或 `uv run` 搭这个环境：它们不会自动把本地主项目源码作为依赖。用 `uv pip` 显式安装本地路径。

## 7. 在规则中使用

`demo/rule.yaml`：

```yaml
name: prefix_example
parse:
  - template: "{title}"
extensions:
  - name: example:prefix_title
    inputs:
      title: title
    outputs:
      title: archive_title
    options:
      prefix: "Archive_"
render:
  - template: "{archive_title}"
```

- `inputs` 左边是能力端口，右边是规则字段；所有输入端口都要绑定。
- `outputs` 左边是能力端口，右边是新字段名；只绑定需要的端口，字段名必须是合法标识符。
- `options` 是传给 `extend` 的常量配置；它会递归冻结，列表在插件中表现为元组。
- 字段表达式可以带加工链，例如 `title:trim|lower`；端口名不能带加工链。
- 扩展可以互相引用，执行顺序由依赖决定，不由书写顺序决定。
- 扩展按需执行：只有 `render`、`condition` 或其他扩展需要某个输出时，才会计算它。
- 扩展节点不能写 `condition`；需要分支时在 `render` 中配置条件。

运行预览：

```powershell
.\.venv\Scripts\sr.exe run --dir demo\examples --rule demo\rule.yaml --dry-run
```

## 8. 系统字段

能力可以声明需要的文件信息，主程序会在调用前自动读取。把下面的声明放在能力类中：

```python
from types import MappingProxyType

from sr.core.contracts.extender import Extender
from sr.core.system import SystemField


class Example(Extender):
    # 其他声明省略
    system_bindings = MappingProxyType(
        {
            "path": SystemField.FILE_PATH,
            "suffix": SystemField.FILE_SUFFIX,
        }
    )
```

可用字段：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `FILE_PATH` | `Path` | 当前文件路径 |
| `FILE_NAME` | `str` | 文件名，含后缀 |
| `FILE_STEM` | `str` | 不含后缀的文件名 |
| `FILE_SUFFIX` | `str` | 小写后缀，如 `.mkv` |
| `FILE_PARENT` | `Path` | 父目录 |
| `FILE_PARENT_NAME` | `str` | 父目录名 |
| `GROUP_MEMBERS` | `tuple[Path, ...]` | 当前分组的所有文件 |
| `RULE_NAME` | `str` | 规则名 |

用 `supports` 判断是否适用：

```python
def supports(self, system_values: Mapping[str, SystemValue]) -> bool:
    return system_values["suffix"] in {".mkv", ".mp4"}
```

不重写 `supports` 时默认对所有文件适用。返回值必须是 `bool`；`supports` 在绑定阶段按文件调用，应保持轻量。返回 `False` 表示跳过该能力；读取失败、探测失败等错误必须抛出，不能用 `False` 掩盖。

## 9. 使用宿主资源

需要网络或媒体探测时，声明 `required_resources` 并重写 `create`：

```python
from sr.core.contracts.extender import Extender
from sr.plugin.resources import HttpClient, ResourceValues


class Example(Extender):
    # 其他声明省略
    required_resources = ("http",)

    @classmethod
    def create(cls, *, resources: ResourceValues) -> "Example":
        return cls(resources["http"])

    def __init__(self, http: HttpClient) -> None:
        self._http = http
```

在 `extend` 中调用 `self._http.post_json(...)`。需要媒体探测时，把 `"http"` 换成 `"media"`，把 `HttpClient` 换成 `MediaProbe`，调用 `self._media.probe(str(system_values["path"]))`。

没有资源需求时不需要重写 `create`，默认实现会直接返回 `cls()`。

- `http`：`post_json(url, *, payload)`，返回解析后的 JSON；当前只提供 JSON POST。
- `media`：`probe(path)`，返回 `ffprobe` 的 JSON 结果；需要 PATH 中有 `ffprobe`。
- `ffprobe` 是外部程序，不属于 Python 依赖，需要在插件安装说明中列给用户。
- 资源由主程序创建和关闭，插件不要自行关闭。
- 预览也会执行能力，因此 `--dry-run` 仍可能发起网络请求或调用 `ffprobe`。
- 媒体探测失败应报错，不要静默返回空值。

`create` 的实例在一批任务中共享，可能被不同组并发调用；资源引用可以保存在实例上，但每次调用的数据不要保存。

## 10. 错误与调试

- 输入、选项或外部数据不合法时抛 `ValueError`；类型不符抛 `TypeError`。
- 不要吞掉宿主或资源抛出的异常，让错误显示在预览结果里。
- 输出字段名不要与已有捕获或其他输出重复；同名但值不同会报错。
- 提示 `未知拓展：example:prefix_title` 时，依次检查：
    1. 运行的是不是 `.venv\Scripts\sr.exe`；
    2. 入口点是否存在；
    3. 领域名和能力名是否拼对；
    4. 输入输出端口是否与声明一致。

检查入口点：

```powershell
.\.venv\Scripts\python.exe -c "from importlib.metadata import entry_points; print([(e.name, e.value) for e in entry_points(group='sr.plugins')])"
```

应看到（至少包含）：

```text
[('example', 'extenders:DOMAIN')]
```

## 参考实现

完整示例见 `sr-plugin-anime`：

- `extenders/bangumi.py`：`http` 资源、`create` 和网络请求。
- `extenders/file_resolution.py`：`system_bindings`、`supports` 和 `media` 探测。

仓库地址：<https://github.com/zaixiamomo/sr-plugin-anime>
