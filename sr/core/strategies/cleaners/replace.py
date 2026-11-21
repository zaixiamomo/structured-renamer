"""子串替换清洗器。"""

from sr.core.contracts.strategies import Cleaner


class Replace(Cleaner):
    """把固定子串替换为新文本。"""

    name = "replace"

    def __init__(self, old: str, new: str) -> None:
        """校验替换参数。

        Args:
            old: 待替换文本，不能为空。
            new: 替换文本。
        Raises:
            TypeError: 参数不是字符串。
            ValueError: old 为空。
        """
        if type(old) is not str or type(new) is not str:
            raise TypeError("replace 参数必须是字符串")
        if not old:
            raise ValueError("replace 的待替换文本不能为空")
        self.old, self.new = old, new

    def _clean(self, text: str) -> str:
        """替换全部匹配文本。"""
        return text.replace(self.old, self.new)
