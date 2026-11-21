"""英文字母捕获类别。"""

from sr.core.contracts.strategies import Classifier


class English(Classifier):
    """匹配 ASCII 英文字母。"""

    name = "en"
    ranges = "a-zA-Z"
