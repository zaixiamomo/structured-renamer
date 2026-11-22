from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sr.app.errors import ApplicationError
from sr.app.models import Batch, Change
from sr.app.protocols import FileSystem, RuleCodec
from sr.core.compile.rule import Rule
from sr.core.run import run_compiled
from sr.core.runtime.state import FileState
from sr.plugin import ExtenderResources, PluginCatalog


class RenamePlanner:
    """扫描目录并按规则生成 rename 批次。"""

    def __init__(
        self,
        filesystem: FileSystem,
        codec: RuleCodec,
        *,
        catalog: PluginCatalog | None = None,
        resources: ExtenderResources | None = None,
        max_workers: int = 8,
    ) -> None:
        """保存计划所需的端口与拓展资源。

        Args:
            filesystem: 文件系统端口。
            codec: 规则编解码端口。
            catalog: 插件能力目录；省略时使用空目录。
            resources: 拓展资源；省略时使用无资源集合。
            max_workers: 分组求值线程数，必须是正整数。
        Raises:
            ValueError: max_workers 不是正整数。
        """
        if type(max_workers) is not int or max_workers < 1:
            raise ValueError("max_workers 必须是正整数")
        self._filesystem = filesystem
        self._codec = codec
        self._catalog = PluginCatalog() if catalog is None else catalog
        self._resources = ExtenderResources() if resources is None else resources
        self._max_workers = max_workers

    def rename(self, directory: Path, rule: Rule | Path | str) -> Batch:
        """扫描目录、运行规则并生成 forward 批次。

        Args:
            directory: 待处理目录。
            rule: Rule 对象或 YAML 规则文件路径。
        Returns:
            包含全部扫描文件与逐项错误的 Batch。
        Raises:
            ApplicationError: 核心路径映射无法区分文件名的大小写。
            OSError: 读取规则或访问文件系统失败。
            ValueError: 规则解析或编译失败。
            PipelineError: 核心管线前置条件不满足。
        """
        excluded: tuple[Path, ...] = ()
        if not isinstance(rule, Rule):
            rule_path = Path(rule).expanduser().absolute()
            rule = self._codec.decode(self._filesystem.read(rule_path))
            # 规则文件本身不参与扫描，避免被当作待改名文件。
            excluded += (rule_path,)
        paths = self._filesystem.scan(directory, excluded)
        # WindowsPath 判等忽略大小写，重复快照意味着核心无法区分这些文件。
        snapshots = {path: self._filesystem.stat(path) for path in paths}
        if len(snapshots) != len(paths):
            raise ApplicationError("当前核心路径映射无法区分这些文件的大小写")
        results = self._evaluate(paths, rule)
        changes: list[Change] = []
        for path, result in results.items():
            target, error = None, result.error
            if error is None:
                try:
                    if result.result is None:
                        raise ValueError("核心未返回名称主体")
                    # 核心只生成名称主体，原后缀统一保留。
                    target = path.with_name(result.result + path.suffix)
                except ValueError as exc:
                    error = exc
            changes.append(Change(path, target, None, snapshots[path], error))
        return Batch(
            id=uuid4().hex,
            dir=directory,
            direction="forward",
            status="running",
            updated=datetime.now(timezone.utc),
            changes=tuple(changes),
        )

    def _evaluate(
        self, paths: tuple[Path, ...], rule: Rule
    ) -> Mapping[Path, FileState]:
        """编译规则、创建所需拓展并运行核心管线。"""
        compiled = rule.compile(extenders=self._catalog.extenders)
        required = (
            node.name for producers in compiled.producers.values() for node in producers
        )
        extenders = self._catalog.create_batch(required, self._resources)
        return run_compiled(
            paths, (compiled,), extenders=extenders, max_workers=self._max_workers
        )
