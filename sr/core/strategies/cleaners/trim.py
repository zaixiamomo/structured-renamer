"""去空白清洗器。"""

from sr.core.contracts.strategies import Cleaner


class Trim(Cleaner):
    """去除首尾空白。"""

    name = "trim"

    def _clean(self, text: str) -> str:
        """去除首尾空白。"""
        return text.strip()
