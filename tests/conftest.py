"""Pytest fixtures and mock classes."""

import pytest
from typing import Any, List, Optional
from pydantic import BaseModel, Field

from edith.agent.state import ConversationMemory
from edith.logging import AuditLogger
from edith.tools.base import Tool, ToolRegistry, ToolResult


class DummyTimeInput(BaseModel):
    timezone: str = Field(..., description="Timezone name like UTC or EST")


class DummyTimeTool(Tool):
    """Dummy tool for testing tool layer and agent loop."""

    name = "get_time"
    description = "Returns current time in specified timezone."
    input_model = DummyTimeInput
    risk_level = "read"

    def run(self, args: DummyTimeInput) -> ToolResult:
        return ToolResult(success=True, data=f"Current time in {args.timezone} is 12:00 PM")


class MockContentBlock:
    def __init__(self, block_type: str, text: Optional[str] = None, id: Optional[str] = None, name: Optional[str] = None, input_args: Optional[dict] = None) -> None:
        self.type = block_type
        self.text = text
        self.id = id
        self.name = name
        self.input = input_args or {}


class MockUsage:
    def __init__(self, input_tokens: int = 15, output_tokens: int = 25) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class MockResponse:
    def __init__(self, content: List[Any], stop_reason: str = "end_turn") -> None:
        self.content = content
        self.stop_reason = stop_reason
        self.usage = MockUsage()


class MockAnthropicClient:
    """Mock client simulating Anthropic Claude responses in sequence."""

    def __init__(self, planned_responses: List[MockResponse]) -> None:
        self.planned_responses = planned_responses
        self.calls = []
        self.messages = self

    def create(self, **kwargs) -> MockResponse:
        self.calls.append(kwargs)
        if not self.planned_responses:
            raise RuntimeError("MockAnthropicClient ran out of planned responses!")
        return self.planned_responses.pop(0)


@pytest.fixture
def tmp_audit_logger(tmp_path) -> AuditLogger:
    log_file = tmp_path / "test_edith.jsonl"
    return AuditLogger(log_path=str(log_file))


@pytest.fixture
def empty_memory() -> ConversationMemory:
    return ConversationMemory(max_turns=10)

