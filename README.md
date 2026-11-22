# structured-renamer

结构化批量重命名工具：通过 YAML 规则从文件名中提取字段，再组合成统一的新名称，支持预览、执行、撤销与重做。

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

> 0.x alpha：CLI、YAML 规则、状态格式和插件 API 可能变化。

## 示例

`demo/` 是一个最小示例，仅演示字段换位、序号补零和空格替换：

```text
demo/examples
├── Alpha - 1 - Sample A.txt   ->  001_Alpha_Sample_A.txt
├── Alpha - 12 - Sample B.txt  ->  012_Alpha_Sample_B.txt
└── Beta - 3 - Sample C.txt    ->  003_Beta_Sample_C.txt
```

`demo/rule.yaml`：

```yaml
name: example
parse:
  - template: "{category} - {index} - {title}"
render:
  - template: '{index:zpad(3)}_{category}_{title:replace(" ", "_")}'
```

`parse` 提取 `category`、`index` 和 `title`；`render` 将序号移到最前面，用 `zpad(3)` 补齐三位，用 `replace(" ", "_")` 替换标题中的空格，再以 `_` 连接字段。最后一个后缀自动保留。

安装后可运行以下命令预览示例：

```powershell
sr run --dir demo/examples --rule demo/rule.yaml --dry-run
```

第一次编写规则可阅读[规则教程](docs/rule-tutorial.md)；完整语法与约定见[规则参考手册](docs/rule-reference.md)。

## 适用范围

- 目前支持 Windows
- 只重命名普通文件；目录会递归遍历，但不会被改名；符号链接会跳过
- 只做同目录改名，不跨目录、不跨磁盘

## 安装

需要 Python 3.10+、Git 和 uv。

从源码安装：

```powershell
git clone https://github.com/zaixiamomo/structured-renamer.git
cd structured-renamer
uv tool install .
sr --version
```

`uv tool install` 把 `sr` 安装到用户级工具环境，之后在任意目录都可以直接运行 `sr`。

卸载：

```powershell
uv tool uninstall structured-renamer
```

## 使用

```powershell
sr --version
sr run --dir DIRECTORY --rule RULE_FILE --dry-run [--no-color]
sr run --dir DIRECTORY --rule RULE_FILE [--no-color]
sr undo [--id ID] [--dry-run] [--no-color]
sr redo [--id ID] [--dry-run] [--no-color]
sr log [--dir DIRECTORY | --id ID] [--no-color]
```

`run` 按规则生成改名计划。`--dry-run` 只预览，不修改文件；正式执行时，单个文件失败不会影响其他文件。存在未完成批次时，`run` 会停止执行，包括 `--dry-run` 预览，并打印该批次的摘要和恢复命令。

`undo` 撤销最近一次完成的改名，`redo` 重做最近一次撤销；两者用 `--id` 指定批次，省略时分别选择最新完成批次和 redo 栈顶批次。存在未完成批次时，二者会优先恢复该批次。`--id` 接受完整 ID 或唯一前缀，前缀不区分大小写；匹配多个批次时会列出候选并拒绝执行。

`log` 从新到旧列出批次，默认显示 `状态 | 8 位短 ID | 本地时间 | 目录`，可用 `--dir` 过滤目录，或用 `--id` 查看指定批次的文件树。状态包括 `已完成`、`可重做`、`已撤销` 和 `未完成`。

`--no-color` 关闭彩色输出，默认按终端能力自动判断；`log` 只给状态字段着色，提示信息使用黄色，意外错误使用红色。
状态默认保存在用户应用数据目录，可用 `SR_STATE_DIR` 指定。
退出码：0 成功，1 运行错误，2 参数错误，130 安全取消。

## 插件

支持安装插件扩展规则能力。准备主项目和插件源码，将两者安装到同一个工具环境：

```powershell
uv tool install "D:\path\to\structured-renamer" --with "D:\path\to\plugin"
```

安装后即可在规则的 `extensions` 中使用插件声明的能力名称。

编写自己的插件可阅读[插件编写教程](docs/plugin-tutorial.md)。

> 参考插件仓库：[sr-plugin-anime](https://github.com/zaixiamomo/sr-plugin-anime)，提供番剧领域相关能力。

## License

[MIT](LICENSE)
