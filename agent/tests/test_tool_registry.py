# ruff: noqa: E402

from pathlib import Path
import sys

from pydantic import BaseModel, ConfigDict
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models import ToolExecutionResult
from app.tool_registry import clear_tools, register_tool


class _Params(BaseModel):
    value: str

    model_config = ConfigDict(frozen=True)


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    clear_tools()
    yield
    clear_tools()


async def _handler(_params: BaseModel) -> ToolExecutionResult:
    return ToolExecutionResult(success=True)


def test_register_tool_duplicate_name_raises() -> None:
    register_tool(name="dup_tool", description="first", param_model=_Params)(_handler)

    with pytest.raises(ValueError, match="already registered"):
        register_tool(name="dup_tool", description="second", param_model=_Params)(
            _handler
        )
