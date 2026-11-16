"""GUI 入口：启动时加载持久化库，进入空窗口（用户导入文件夹后填充文件树）"""

import sys

from .app import run


def main() -> int:
    return run()  # 空树，用户经导入填充


if __name__ == "__main__":
    sys.exit(main())
