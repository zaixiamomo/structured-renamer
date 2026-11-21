"""核心管线错误。"""


class PipelineError(RuntimeError):
    """规则编译或管线契约错误。"""


class FileError(RuntimeError):
    """归属单个文件的阶段错误。"""

    def __init__(self, stage: str, cause: Exception) -> None:
        """记录出错阶段并保留原始异常。

        受影响成员由 PipelineContext.files 的键确定，同一个 FileError 可关联多个文件。

        Args:
            stage: 发生错误的管线阶段。
            cause: 原始异常。
        """
        self.stage = stage
        self.cause = cause
        super().__init__(f"{stage}: {cause}")
        self.__cause__ = cause
