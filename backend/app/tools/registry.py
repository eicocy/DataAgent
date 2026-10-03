from dataclasses import dataclass
from pydantic import BaseModel


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    schema: type[BaseModel]
    version: str = '2.0'
    metadata: object | None = None


def tool_registry(permissions=None) -> dict[str, ToolSpec]:
    from app.analysis.catalog import build_registry
    return {tool.metadata.name:ToolSpec(tool.metadata.name,tool.metadata.description,tool.input_schema,tool.metadata.version,tool.metadata)
            for tool in build_registry(include_legacy=True).list_tools() if tool.metadata.chat_enabled and not tool.metadata.modifies_dataset and (permissions is None or tool.metadata.permissions<=permissions)}


def validate_arguments(name: str, arguments: dict) -> BaseModel:
    registry = tool_registry()
    if name not in registry:
        raise ValueError('unknown tool')
    return registry[name].schema.model_validate(arguments)
