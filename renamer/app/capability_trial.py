"""单项能力试跑：转换输入字段并将能力输出投影为编辑预览值"""

from collections.abc import Mapping

from renamer.core.model import CapabilityFn, FieldKey


class CapabilityTrial:
    def __init__(self, calls: Mapping[str, CapabilityFn]) -> None:
        self._calls = calls

    def run(self, cap_id: str, inputs: dict[str, str]) -> dict[str, str]:
        """缺失实现、非法输出或插件异常均按无产出处理"""
        try:
            fn = self._calls.get(cap_id)
            if fn is None:
                return {}
            result = fn({FieldKey.parse(key): value for key, value in inputs.items()})
            if not isinstance(result, Mapping):
                return {}
            return {str(key): str(value) for key, value in result.items()}
        except Exception:  # noqa: BLE001 插件信任边界，保留试跑的空结果降级
            return {}
