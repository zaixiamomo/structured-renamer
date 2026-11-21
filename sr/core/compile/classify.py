"""捕获类别 DSL 的编译。"""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from sr.core.contracts.compilable import Compilable
from sr.core.contracts.strategies import Classifier
from sr.core.strategies import CLASSIFIERS


@dataclass(frozen=True)
class CompiledClassify:
    """一组可叠加的字符类别。"""

    classifiers: tuple[Classifier, ...]

    @property
    def ranges(self) -> str:
        """合并所有类别的正则字符类内容。"""
        return "".join(classifier.ranges for classifier in self.classifiers)

    @property
    def size(self) -> int:
        """返回合并后类别覆盖的码点数量。"""
        return _range_size(self.ranges)

    def matches(self, char: str) -> bool:
        """判断字符是否命中任一类别；空类别匹配全部。"""
        return not self.classifiers or any(
            classifier.matches(char) for classifier in self.classifiers
        )


def _range_intervals(ranges: str) -> tuple[tuple[int, int], ...]:
    """把 a-z 形式的范围文本解析为闭区间。"""
    intervals: list[tuple[int, int]] = []
    index = 0
    while index < len(ranges):
        start = ord(ranges[index])
        if index + 2 < len(ranges) and ranges[index + 1] == "-":
            end = ord(ranges[index + 2])
            if end < start:
                raise ValueError("字符类别范围非法")
            intervals.append((start, end))
            index += 3
        else:
            intervals.append((start, start))
            index += 1
    return tuple(intervals)


def _range_size(ranges: str) -> int:
    """统计合并重叠区间后的码点总数。"""
    total = 0
    current_start = current_end = -1
    # 先排序再合并，避免重复范围和跨范围重叠被重复计数。
    for start, end in sorted(_range_intervals(ranges)):
        if current_start < 0:
            current_start, current_end = start, end
        elif start <= current_end + 1:
            current_end = max(current_end, end)
        else:
            total += current_end - current_start + 1
            current_start, current_end = start, end
    if current_start >= 0:
        total += current_end - current_start + 1
    return total


class Classify(BaseModel, Compilable[CompiledClassify]):
    """en/digits/cn 等捕获类别声明。"""

    text: str

    model_config = ConfigDict(frozen=True, extra="forbid")

    def __init__(self, text: str) -> None:
        """接受斜杠分隔的类别表达式。"""
        super().__init__(text=text)

    def compile(self) -> CompiledClassify:
        """编译斜杠分隔的类别表达式。

        Returns:
            CompiledClassify；每个斜杠分隔项都必须是已注册类别。
        Raises:
            ValueError: 类别名未知。
        """
        classifiers: list[Classifier] = []
        for part in self.text.split("/"):
            name = part.strip()
            classifier_type = CLASSIFIERS.get(name)
            if classifier_type is None:
                raise ValueError(f"未知捕获类别：{name}")
            classifiers.append(classifier_type())
        return CompiledClassify(tuple(classifiers))
