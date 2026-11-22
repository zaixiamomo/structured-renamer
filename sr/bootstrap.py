from sr.adapters.filesystem import LocalFileSystem
from sr.adapters.http_client import JsonHttpClient
from sr.adapters.media_probe import FfprobeClient
from sr.adapters.state_store import LocalStateStore
from sr.adapters.yaml_codec import YamlCodec
from sr.app.service import RenameService
from sr.core.strategies.extenders import DOMAIN as BUILTIN
from sr.plugin import ExtenderResources, PluginCatalog
from sr.settings import Settings


def assemble_application(
    settings: Settings | None = None,
) -> RenameService:
    """按配置组装 RenameService 及默认适配器。

    Args:
        settings: 运行配置；省略时使用 Settings() 的默认值。
    Returns:
        已绑定本地文件系统、YAML 编解码、状态存储和插件目录的服务。
    """
    settings = settings or Settings()
    return RenameService(
        filesystem=LocalFileSystem(),
        codec=YamlCodec(),
        store=LocalStateStore(settings.state_dir),
        max_workers=settings.max_workers,
        # 内置领域随进程提供，其余领域从 sr.plugins 入口发现。
        catalog=PluginCatalog.discover((BUILTIN,)),
        resources=ExtenderResources(
            http=JsonHttpClient(
                timeout=settings.http_timeout,
                user_agent=settings.http_user_agent,
                min_interval=settings.http_min_interval,
            ),
            media=FfprobeClient(
                executable=settings.ffprobe_executable,
                timeout=settings.ffprobe_timeout,
            ),
        ),
    )
