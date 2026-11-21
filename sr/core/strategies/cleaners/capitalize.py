"""首字母大写清洗器。"""

from sr.core.contracts.strategies import Cleaner


class Capitalize(Cleaner):
    """首字符大写、其余小写。"""

    name = "capitalize"

    def _clean(self, text: str) -> str:
        """将文本首字母转为大写。"""
        return text.capitalize()
