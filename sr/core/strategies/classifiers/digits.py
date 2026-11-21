"""数字捕获类别。"""

from sr.core.contracts.strategies import Classifier


class Digits(Classifier):
    """匹配 0-9。"""

    name = "digits"
    ranges = "0-9"
