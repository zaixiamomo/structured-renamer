"""大写清洗器。"""

from sr.core.contracts.strategies import Cleaner


class Upper(Cleaner):
    """转为大写。"""

    name = "upper"

    def _clean(self, text: str) -> str:
        """把文本转为大写。"""
        return text.upper()
