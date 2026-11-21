"""插件领域发现与拓展能力注册。"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from importlib.metadata import entry_points
from inspect import isabstract
from types import MappingProxyType

from sr.core.contracts.extender import Extender
from sr.core.system import check_system_bindings
from sr.plugin.resources import ExtenderResources, check_required_resources


@dataclass(frozen=True)
class Domain:
    """一组可注册到同一命名空间的拓展声明。"""

    name: str
    extenders: tuple[type[Extender], ...] = ()

    def __post_init__(self) -> None:
        """校验领域名称并冻结能力元组。"""
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("领域名称必须是非空文本")
        if ":" in self.name:
            raise ValueError("领域名称不能包含冒号")
        object.__setattr__(self, "extenders", tuple(self.extenders))


@dataclass(frozen=True, init=False)
class PluginCatalog:
    """按完整名称索引的拓展类目录。"""

    extenders: Mapping[str, type[Extender]]

    def __init__(self, domains: Iterable[Domain] = ()) -> None:
        """校验并登记领域及其能力。

        Args:
            domains: 待登记领域；为空时得到空目录。
        Raises:
            TypeError: 领域或能力类型不符。
            ValueError: 领域或能力重名、名称非法、端口声明非法。
        """
        domains = tuple(domains)
        names: set[str] = set()
        for domain in domains:
            if not isinstance(domain, Domain):
                raise TypeError("领域入口必须是 Domain")
            if domain.name in names:
                raise ValueError(f"重复领域：{domain.name}")
            names.add(domain.name)
        types: dict[str, type[Extender]] = {}
        for domain in domains:
            for implementation in domain.extenders:
                if (
                    not isinstance(implementation, type)
                    or not issubclass(implementation, Extender)
                    or isabstract(implementation)
                ):
                    raise TypeError("领域能力必须是具体的 Extender 类")
                name = getattr(implementation, "name", None)
                if not isinstance(name, str) or not name.strip():
                    raise ValueError("能力名称必须是非空文本")
                if ":" in name:
                    raise ValueError("能力短名称不能包含冒号")
                # 完整能力名采用 domain:name，避免跨领域重名。
                qualified_name = f"{domain.name}:{name}"
                if qualified_name in types:
                    raise ValueError(f"重复能力：{qualified_name}")
                self._check_ports(implementation)
                check_system_bindings(implementation.system_bindings)
                check_required_resources(implementation.required_resources)
                types[qualified_name] = implementation
        object.__setattr__(self, "extenders", MappingProxyType(types))

    @classmethod
    def discover(cls, domains: Iterable[Domain] = ()) -> "PluginCatalog":
        """加载给定领域并追加 sr.plugins 入口发现的领域。

        Args:
            domains: 进程内直接提供的领域，先于入口点登记。
        Returns:
            合并后的 PluginCatalog，不创建实例。
        Raises:
            TypeError: 入口点未提供 Domain 或能力声明类型错误。
            ValueError: 领域或能力名称重复、声明无效。
        """
        discovered = list(domains)
        for entry in sorted(
            entry_points(group="sr.plugins"), key=lambda item: (item.name, item.value)
        ):
            domain = entry.load()
            if not isinstance(domain, Domain):
                raise TypeError(
                    f"插件入口 {entry.name} ({entry.value}) 必须提供 Domain"
                )
            discovered.append(domain)
        return cls(discovered)

    def create_batch(
        self, required: Iterable[str], resources: ExtenderResources
    ) -> Mapping[str, Extender]:
        """为一批任务创建所需的 Extender 实例。

        Args:
            required: 本批需要的完整能力名；重复项会合并。
            resources: 批次级资源入口。
        Returns:
            能力名到实例的只读映射。
        Raises:
            TypeError: 能力创建结果不是 Extender。
            ValueError: 能力未知、所需资源未配置，或实例声明与类声明不一致。
        """
        # 每批使用独立的 HTTP 缓存，避免跨批复用响应。
        resources = resources.for_batch()
        selected = tuple(dict.fromkeys(required))
        unknown = set(selected) - self.extenders.keys()
        if unknown:
            raise ValueError(f"未知拓展：{sorted(unknown)}")
        resources_by_name = {
            name: resources.select(self.extenders[name].required_resources)
            for name in selected
        }
        instances = {}
        for name in selected:
            extender_type = self.extenders[name]
            instance = extender_type.create(resources=resources_by_name[name])
            if not isinstance(instance, Extender):
                raise TypeError(f"能力创建必须返回 Extender：{name}")
            if (
                instance.name != extender_type.name
                or instance.input_ports != extender_type.input_ports
                or instance.output_ports != extender_type.output_ports
                or check_system_bindings(instance.system_bindings)
                != check_system_bindings(extender_type.system_bindings)
            ):
                raise ValueError(f"能力实例的名称或端口与声明不一致：{name}")
            instances[name] = instance
        return MappingProxyType(instances)

    @staticmethod
    def _check_ports(extender_type: type[Extender]) -> None:
        """校验端口声明为不重复的非空字符串元组。"""
        for attribute in ("input_ports", "output_ports"):
            ports = getattr(extender_type, attribute, None)
            if not isinstance(ports, tuple) or any(
                not isinstance(port, str) or not port.strip() for port in ports
            ):
                raise ValueError(
                    f"能力 {extender_type.name} 的 {attribute} 必须是文本元组"
                )
            if len(ports) != len(set(ports)):
                raise ValueError(f"能力 {extender_type.name} 的 {attribute} 含重复端口")
