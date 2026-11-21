"""中文捕获类别。"""

from sr.core.contracts.strategies import Classifier


class Chinese(Classifier):
    """匹配常用中文汉字。"""

    name = "cn"
    ranges = "\u4e00-\u9fff"
