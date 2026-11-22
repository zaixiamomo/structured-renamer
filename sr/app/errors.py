"""可以展示给调用者的应用错误。"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sr.app.models import Batch


class ApplicationError(RuntimeError):
    """应用操作失败。"""


class UnfinishedBatchError(ApplicationError):
    """存在未完成批次，拒绝开始新的改名。"""

    def __init__(self, batch: "Batch") -> None:
        """保存未完成批次，供调用方展示和提示恢复命令。"""
        self.batch = batch
        super().__init__(f"目录 {batch.dir} 有未完成批次 {batch.short_id}")


class StateWriteError(ApplicationError):
    """状态写入失败或无法确定提交结果。"""


class RollbackError(ApplicationError):
    """操作失败且未能完整恢复，携带失败位置。"""

    def __init__(self, cause: BaseException, failures: tuple[str, ...]) -> None:
        """保存原始异常与未能恢复的具体位置。"""
        self.cause = cause
        self.failures = failures
        super().__init__(f"操作失败：{cause}；未能完整恢复：" + "；".join(failures))
