from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .core.model import (
    SOURCE_PATH_KEY,
    Capability,
    CapabilityCall,
    CapabilityResult,
    Channel,
    Field,
    FieldKey,
    FieldType,
    FileResult,
    Issue,
    Level,
    PlanError,
    Report,
    ReportSummary,
    Rule,
    Status,
    Template,
    TokenMapping,
)

__all__ = [
    "SOURCE_PATH_KEY",
    "Capability",
    "CapabilityCall",
    "CapabilityResult",
    "Channel",
    "Field",
    "FieldKey",
    "FieldType",
    "FileResult",
    "Issue",
    "Level",
    "PlanError",
    "Report",
    "ReportSummary",
    "Rule",
    "Status",
    "Template",
    "TokenMapping",
]

try:
    __version__ = version("structured-renamer")
except PackageNotFoundError:
    __version__ = "0.0.0"
