from dataclasses import dataclass
from threading import Lock
from typing import Awaitable, Callable

from pydantic import BaseModel

from app.models import ToolExecutionResult


ToolHandler = Callable[[BaseModel], Awaitable[ToolExecutionResult]]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    param_model: type[BaseModel]
    handler: ToolHandler


_TOOL_REGISTRY: dict[str, ToolSpec] = {}
_TOOL_REGISTRY_LOCK = Lock()


def register_tool(
    name: str,
    description: str,
    param_model: type[BaseModel],
) -> Callable[[ToolHandler], ToolHandler]:
    def decorator(handler: ToolHandler) -> ToolHandler:
        with _TOOL_REGISTRY_LOCK:
            if name in _TOOL_REGISTRY:
                raise ValueError(f"tool '{name}' already registered")
            _TOOL_REGISTRY[name] = ToolSpec(
                name=name,
                description=description,
                param_model=param_model,
                handler=handler,
            )
        return handler

    return decorator


def get_tool(name: str) -> ToolSpec:
    try:
        return _TOOL_REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"tool '{name}' not found") from exc


def list_tools() -> list[ToolSpec]:
    return list(_TOOL_REGISTRY.values())


def clear_tools() -> None:
    with _TOOL_REGISTRY_LOCK:
        _TOOL_REGISTRY.clear()


def register_builtin_tools() -> None:
    from app.tools.query_kline import register_query_kline_tools
    from app.tools.reco_query import register_reco_query_tools
    from app.tools.strategy_tools import register_strategy_tools
    from app.tools.technical import register_technical_tools

    register_query_kline_tools()
    register_technical_tools()
    register_reco_query_tools()
    register_strategy_tools()
