# 规则编写教程

> 适用版本：0.2.x（alpha） · UTF-8 YAML · Windows

这篇教程用同一批资料逐步演示规则的主要能力，完整语法和执行约定见[规则参考手册](rule-reference.md)。

全文整理的是同一批资料：`category` 表示类别，`index` 表示序号，`title` 表示标题。后面会为这些资料增加标记和配套 JSON 文件，但字段的含义保持不变。

## 阅读路线

1. [先把序号移到前面](#先把序号移到前面)
2. [让序号和标题更整齐](#让序号和标题更整齐)
3. [接收另一种文件名格式](#接收另一种文件名格式)
4. [给带标记的资料选择不同输出](#给带标记的资料选择不同输出)
5. [让配套文件补齐标题](#让配套文件补齐标题)
6. [把简写标记换成完整名称](#把简写标记换成完整名称)

前六节中的主要 YAML 示例都可以独立作为规则文件使用。每节给出的原名都是该节的输入，不是上一节改名后的文件；先用原名理解效果，再把写法用于实际文件。

## 先把序号移到前面

从三个文件开始，将序号放在最前面：

```text
Alpha - 1 - Sample A.txt   ->  1-Alpha-Sample A.txt
Alpha - 12 - Sample B.txt  ->  12-Alpha-Sample B.txt
Beta - 3 - Sample C.txt    ->  3-Beta-Sample C.txt
```

把下面的内容保存为 UTF-8 编码的 `rule.yaml`：

```yaml
name: organize_samples
parse:
  - template: "{category} - {index} - {title}"
render:
  - template: "{index}-{category}-{title}"
```

`parse` 描述原名的结构。以第一个文件为例：

| 原名中的部分 | 保存到的字段 |
| --- | --- |
| `Alpha` | `category` |
| `1` | `index` |
| `Sample A` | `title` |

花括号里的名字可以自定义；花括号外的 ` - ` 是原名中实际存在的分隔文字，空格也参与匹配。

`render` 按字段名取出这些值，重新拼接。这里用 `{index}` 把序号放在前面，再用短横线连接类别和标题。提取与引用的字段名必须一致。

`.txt` 不写进模板：模板处理名称主体，最后一个后缀会自动接回。新文件仍在原目录，模板不能指定路径。

`parse` 和 `render` 都是列表，每个 `- template:` 是一个分支。当前各写一条即可。解析时需要匹配整个名称主体。

字段名区分大小写，提取和引用保持一致。更多写法见[模板](rule-reference.md#模板)和[词段](rule-reference.md#词段)。

## 让序号和标题更整齐

接下来希望序号统一补到三位，并把标题中的空格换成下划线：

```text
Alpha - 1 - Sample A.txt   ->  001_Alpha_Sample_A.txt
Alpha - 12 - Sample B.txt  ->  012_Alpha_Sample_B.txt
Beta - 3 - Sample C.txt    ->  003_Beta_Sample_C.txt
```

在输出字段后加上 `:操作`：

```yaml
name: organize_samples
parse:
  - template: "{category} - {index} - {title}"
render:
  - template: '{index:zpad(3)}_{category}_{title:replace(" ", "_")}'
```

`zpad(3)` 把序号补到至少三位；`replace(" ", "_")` 把标题中的空格替换为下划线。外层 YAML 字符串使用单引号，里面的操作参数就可以直接使用双引号。

### 一个字段需要多步加工时

假如标题两端还可能有多余空格，希望先去掉，再替换中间的空格，可以把输出模板中的标题写成：

```text
{title:trim|replace(" ", "_")}
```

`|` 连接的操作从左到右执行，称为加工链：

```text
" Sample A "  ->  trim  ->  "Sample A"  ->  replace(" ", "_")  ->  "Sample_A"
```

### 加工后的值要不要留给后续使用

目前的加工都写在 `render` 中，只影响这一次输出。如果希望后续条件、分组等也读到加工后的值，就把加工写在 `parse` 的字段上。

例如，希望统一保存小写类别：

```yaml
name: organize_samples
parse:
  - template: "{category:lower} - {index} - {title}"
render:
  - template: '{index:zpad(3)}_{category}_{title:trim|replace(" ", "_")}'
```

```text
Alpha - 1 - Sample A.txt  ->  001_alpha_Sample_A.txt
```

这里保存的 `category` 已经是 `alpha`。后文继续采用这种写法。

### 限定序号只能从数字中提取

补零本身不会检查数字；`abc` 经过 `zpad(5)` 也会得到 `00abc`。如果原名中的序号应该只包含数字，在解析时写 `{index=digits}`：

```yaml
name: organize_samples
parse:
  - template: "{category:lower} - {index=digits} - {title}"
render:
  - template: '{index:zpad(3)}_{category}_{title:trim|replace(" ", "_")}'
```

`=digits` 限定原名里这一段只能包含 ASCII 数字 `0`–`9`。提取后保存的仍是文本，例如 `"1"`，没有变成整数。

字段的基本写法至此就是：

```text
{字段名=字符类别:加工链}
```

字符类别和加工链都可以省略。更多操作和执行位置见[加工链](rule-reference.md#加工链)，其他字符类别见[词段](rule-reference.md#词段)。

## 接收另一种文件名格式

同一批资料有时使用下划线分隔。这两种原名需要得到统一的输出：

```text
Alpha - 1 - Sample A.txt  ->  001_alpha_Sample_A.txt
Alpha_12_Sample B.txt     ->  012_alpha_Sample_B.txt
Beta - 3 - Sample C.txt   ->  003_beta_Sample_C.txt
```

增加一个解析分支，使用相同的字段名：

```yaml
name: organize_samples
parse:
  - template: "{category:lower} - {index=digits} - {title}"
  - template: "{category:lower}_{index=digits}_{title}"
render:
  - template: '{index:zpad(3)}_{category}_{title:trim|replace(" ", "_")}'
```

两个分支都提供 `category`、`index` 和 `title`，所以可以共用同一条输出模板。

解析分支不会按列表顺序选第一条，而会选择匹配成功且约束最强的分支；最高分并列时会报错。这里两种格式由不同的分隔文字区分。详细选择规则见[分支](rule-reference.md#分支)。

## 给带标记的资料选择不同输出

现在有些资料在标题后多了一个标记，例如 `[A]`。需要保留这个字段，并让标记为 `A` 的资料在输出中加上 `.marked`：

```text
Alpha - 1 - Sample A [A].txt  ->  001_alpha_Sample_A.marked.txt
Alpha_12_Sample B.txt         ->  012_alpha_Sample_B.txt
Beta - 3 - Sample C [B].txt   ->  003_beta_Sample_C.txt
```

为带标记的格式增加解析分支，再为特殊输出添加条件：

```yaml
name: organize_samples
parse:
  - template: "{category:lower} - {index=digits} - {title} [{tag:trim}]"
  - template: "{category:lower} - {index=digits} - {title}"
  - template: "{category:lower}_{index=digits}_{title}"
render:
  - template: '{index:zpad(3)}_{category}_{title:trim|replace(" ", "_")}.marked'
    condition: 'exists(tag) and tag == "A"'
  - template: '{index:zpad(3)}_{category}_{title:trim|replace(" ", "_")}'
```

带标记的原名也可能被普通格式匹配，后者会把 `[A]` 一并收进标题。带标记分支额外限定了方括号及前面的空格，约束更强，因此被选中。

`condition` 决定一个分支是否可用。这里先用 `exists(tag)` 判断有没有标记，再比较标记是否等于 `"A"`。`and` 从左到右判断，前面为假就停止，所以无标记的文件不会直接读取缺失字段。

这里第一条输出处理标记 A，第二条不写条件，作为其余文件的兜底。输出也不是按列表顺序首次命中：候选分支中只能有一个条件为真；没有真条件时，只能有一个无条件分支。

条件读取保存值，例如这里的类别已经转成小写，比较时应写 `category == "alpha"`。更多条件写法见[条件](rule-reference.md#条件)，选择约定见[分支](rule-reference.md#分支)。

## 让配套文件补齐标题

同一份资料还有一个 JSON 配套文件。配套文件只有类别和序号，缺少标题：

```text
Alpha - 1 - Sample A.txt
Alpha - 1.json
```

两个文件需要具有相同的名称主体：

```text
Alpha - 1 - Sample A.txt  ->  001_alpha_Sample_A.txt
Alpha - 1.json            ->  001_alpha_Sample_A.json
```

这一节先用不带标记的资料说明借值。把序号作为分组键，让配套 JSON 从同组 TXT 读取缺少的 `title`：

```yaml
name: organize_samples
parse:
  - template: "{category:lower} - {index=digits} - {title}"
    condition: 'file.suffix == ".txt"'
  - template: "{category:lower}_{index=digits}_{title}"
    condition: 'file.suffix == ".txt"'
  - template: "{category:lower} - {index=digits}"
    condition: 'file.suffix == ".json"'
group:
  - token: index=int
render:
  - template: '{index:zpad(3)}_{category}_{title:trim|replace(" ", "_")}'
```

本例按序号分组，假设同一目录里的每个序号对应一份资料。实际使用时，分组键必须足以区分不相关的文件。

| 文件 | 本地保存的字段 | 从同组文件读取 |
| --- | --- | --- |
| `Alpha - 1 - Sample A.txt` | category、index、title | 无需借值 |
| `Alpha - 1.json` | category、index | title=`Sample A` |

`group` 只关联同一规则、同一父目录下的文件，不跨子目录；供值文件与借值文件必须在同一次运行中处理。

### 为什么这里写 `index=int`

假如配套文件写成 `Alpha - 01.json`，文本 `1` 与 `01` 不相等。`index=int` 把这两个值转换为整数参与分组，因此仍可归到一起。

这与解析中的 `index=digits` 用途不同：

| 写法 | 做什么 |
| --- | --- |
| 解析中的 `{index=digits}` | 限定原名字符，保存的仍是文本 |
| 分组中的 `index=int` | 把保存值转成整数，用于分组 |

分组不修改原字段。输出中的 `index` 仍可能是 `1` 或 `01`，所以继续使用 `zpad(3)` 统一外观。

已有本地值时使用本地值，缺少时才向同组成员借用；多个供值来源需要给出一致的文本。备用键和其他划分方式见[分组](rule-reference.md#分组)。

## 把简写标记换成完整名称

回到资料上的 `[A]`、`[B]` 标记。现在需要把这些标记统一成完整名称：`A`、`a1` 表示 `reviewed`，`B`、`b1` 表示 `draft`。这些对应关系是本例约定，可以按实际需求替换名称。

```text
Alpha - 1 - Sample A [A].txt  ->  001_alpha_Sample_A.reviewed.txt
Alpha_12_Sample B.txt         ->  012_alpha_Sample_B.txt
Beta - 3 - Sample C [B].txt   ->  003_beta_Sample_C.draft.txt
```

使用内置扩展 `builtin:lookup` 查表，把 `tag` 转成新的 `label` 字段。下面把前面学过的格式、条件和配套文件分组放到同一条规则中：

```yaml
name: organize_samples
parse:
  - template: "{category:lower} - {index=digits} - {title} [{tag:trim}]"
    condition: 'file.suffix == ".txt"'
  - template: "{category:lower} - {index=digits} - {title}"
    condition: 'file.suffix == ".txt"'
  - template: "{category:lower}_{index=digits}_{title}"
    condition: 'file.suffix == ".txt"'
  - template: "{category:lower} - {index=digits}"
    condition: 'file.suffix == ".json"'
group:
  - token: index=int
extensions:
  - name: builtin:lookup
    inputs:
      value: "tag:lower"
    outputs:
      value: label
    options:
      reviewed: [a, a1, reviewed]
      draft: [b, b1, draft]
render:
  - template: '{index:zpad(3)}_{category}_{title:trim|replace(" ", "_")}.{label}'
    condition: 'exists(tag) and tag != ""'
  - template: '{index:zpad(3)}_{category}_{title:trim|replace(" ", "_")}'
```

配套 JSON 也可以借用同组的标题和标记。例如，`Alpha - 1.json` 与上面的第一份资料一起处理时，目标名为 `001_alpha_Sample_A.reviewed.json`。本例仍假设每个序号在目录中对应一份资料。

### 如何读懂这段扩展配置

- `name` 选择要使用的能力，这里是内置查表能力。
- `inputs` 把字段接到输入端口。左边的 `value` 是能力规定的端口名；右边的 `tag:lower` 表示读取标记并转成小写。
- `outputs` 把输出端口绑定为字段。这里把返回值保存为 `label`，随后可以用 `{label}` 引用。
- `options` 配置查表关系。键是目标文本，列表是可以接受的别名。

接线中的字段不加花括号。输入加工在调用前执行，输出也可以写成 `label:upper`，在返回后加工。

`lookup` 按完整文本查表，不自行清理空白或大小写。目标文本不会自动加入对应的别名列表，因此示例显式把 `reviewed` 和 `draft` 也放进列表。未列出的输入会报错，不会原样返回。

扩展还可以把一个节点的输出接到另一个节点，也可以使用已安装的外部插件。接线、内置能力和依赖约定见[扩展](rule-reference.md#扩展)。
