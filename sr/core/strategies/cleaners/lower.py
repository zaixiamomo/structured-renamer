"""小写清洗器。"""

from sr.core.contracts.strategies import Cleaner


class Lower(Cleaner):
    """转为小写。"""

    name = "lower"

    def _clean(self, text: str) -> str:
        """把文本转为小写。"""
        return text.lower()
