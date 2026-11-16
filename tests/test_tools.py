"""Tests for Tool abstraction, Pydantic schema generation, and error recovery."""

from edith.tools.base import ToolRegistry
from edith.tools.drive import SearchDriveInput, SearchDriveTool
from tests.conftest import DummyTimeInput, DummyTimeTool


def test_tool_schema_generation():
    tool = DummyTimeTool()
    schema = tool.to_anthropic_schema()

    assert schema["name"] == "get_time"
    assert "timezone" in schema["input_schema"]["properties"]
    assert "required" in schema["input_schema"]
    assert "timezone" in schema["input_schema"]["required"]


def test_tool_valid_execution():
    tool = DummyTimeTool()
    result = tool.validate_and_run({"timezone": "UTC"})
    assert result.success is True
    assert "12:00 PM" in result.data


def test_tool_validation_error_recovery():
    tool = DummyTimeTool()
    # Missing required field 'timezone'
    result = tool.validate_and_run({})
    assert result.success is False
    assert "Argument validation failed" in result.error
    assert "Field required" in result.error or "timezone" in result.error


def test_tool_registry():
    registry = ToolRegistry()
    registry.register(DummyTimeTool())

    assert registry.get("get_time") is not None
    assert registry.get("unknown_tool") is None
    assert len(registry.get_all_schemas()) == 1
    assert registry.is_risk_send("get_time") is False
