"""只读 TOML 的字符串解码与点击区间投影"""

from collections.abc import Iterator
from dataclasses import dataclass


def toml_value_text(line: str) -> str | None:
    """``key = "..."`` 行引号内的原文内容（无闭引号返回 None）"""
    start = line.find('"')
    if start < 0:
        return None
    end = line.rfind('"', start + 1)
    if end < 0:
        return None
    return line[start + 1 : end]


def decode_toml_basic(raw: str) -> tuple[str, list[int], list[int]]:
    """解码 TOML 基本字符串的原始内容，返回明文与每明文字符对应的 raw 起止下标

    emit 用 ``\\ \\" \\n \\r \\t \\uXXXX`` 转义；``starts/ends`` 与 decoded 等长，
    供把明文里的 token 位置换算回 TOML 明文坐标。
    """
    decoded: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    i, n = 0, len(raw)
    while i < n:
        ch = raw[i]
        if ch != "\\" or i + 1 >= n:
            starts.append(i)
            decoded.append(ch)
            ends.append(i)
            i += 1
            continue
        nxt = raw[i + 1]
        if nxt in '\\"':
            code, ln = nxt, 2
        elif nxt == "n":
            code, ln = "\n", 2
        elif nxt == "r":
            code, ln = "\r", 2
        elif nxt == "t":
            code, ln = "\t", 2
        elif nxt == "u" and i + 6 <= n:
            try:
                cp = int(raw[i + 2 : i + 6], 16)
            except ValueError:
                cp = -1
            if 0 <= cp <= 0x10FFFF:
                code, ln = chr(cp), 6
            else:
                code, ln = nxt, 2
        else:
            code, ln = nxt, 2
        starts.append(i)
        decoded.append(code)
        ends.append(i + ln - 1)
        i += ln
    return "".join(decoded), starts, ends


def toml_lines(text: str) -> Iterator[tuple[str, int]]:
    """按现有展示文本逐行提供绝对起点"""
    offset = 0
    for line in text.split("\n"):
        yield line, offset
        offset += len(line) + 1


@dataclass(frozen=True)
class TomlString:
    """已输出基本字符串及解码前后的字符对应关系"""

    raw: str
    decoded: str
    offset: int
    starts: list[int]
    ends: list[int]

    def name_region(self) -> dict:
        return {
            "kind": "name",
            "start": self.offset,
            "end": self.offset + len(self.raw),
        }

    def token_region(self, token_id: int, start: int, end: int) -> dict:
        return {
            "kind": "token",
            "tid": token_id,
            "start": self.offset + self.starts[start],
            "end": self.offset + self.ends[end] + 1,
        }


def toml_string(line: str, offset: int, key: str) -> TomlString | None:
    """只识别当前输出器的单行基本字符串排版"""
    prefix = f'{key} = "'
    if not line.startswith(prefix):
        return None
    raw = toml_value_text(line)
    if raw is None:
        return None
    decoded, starts, ends = decode_toml_basic(raw)
    return TomlString(raw, decoded, offset + len(prefix), starts, ends)
