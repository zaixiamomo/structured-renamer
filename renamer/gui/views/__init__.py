"""视图公开入口，按需导出，避免基础面板导入触发整套主窗口装配"""

from importlib import import_module

__all__ = ["MainWindow", "RulePanel", "TemplatePanel"]

_MODULES = {
    "MainWindow": ".main_window",
    "RulePanel": ".rule_panel",
    "TemplatePanel": ".template_panel",
}


def __getattr__(name: str):
    module_name = _MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value
