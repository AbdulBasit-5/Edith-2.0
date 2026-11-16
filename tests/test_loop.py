"""Tests for the ReAct Agent Loop: tool routing, error recovery, approvals, and limits."""

from edith.agent.loop import AgentLoop
from edith.agent.state import ConversationMemory, LoopStatus
from edith.tools.base import Tool, ToolRegistry, ToolResult
from tests.conftest import (
    DummyTimeTool,
    MockAnthropicClient,
    MockContentBlock,
    MockResponse,
)


def test_plain_model_call_no_tools(empty_memory, tmp_audit_logger):
    """Test: When asking 'what's 2+2', model responds with plain text and no tools are called."""
    empty_memory.add_user_message("What is 2 + 2?")

    mock_client = MockAnthropicClient([
        MockResponse(
            content=[MockContentBlock("text", text="2 + 2 equals 4.")],
            stop_reason="end_turn",
        )
    ])

    registry = ToolRegistry()
    registry.register(DummyTimeTool())

    agent = AgentLoop(
        tool_registry=registry,
        client=mock_client,
        audit_logger=tmp_audit_logger,
    )

    result = agent.run(empty_memory)

    assert result.status == LoopStatus.COMPLETED
    assert result.final_text == "2 + 2 equals 4."
    assert result.iterations_used == 1
    assert len(mock_client.calls) == 1


def test_tool_calling_and_response_cycle(empty_memory, tmp_audit_logger):
    """Test: Model calls get_time tool, receives result, and returns final answer."""
    empty_memory.add_user_message("What time is it in UTC?")

    mock_client = MockAnthropicClient([
        # Step 1: Model requests tool call
        MockResponse(
            content=[
                MockContentBlock(
                    "tool_use",
                    id="tool_call_001",
                    name="get_time",
                    input_args={"timezone": "UTC"},
                )
            ],
            stop_reason="tool_use",
        ),
        # Step 2: Model uses tool result to answer
        MockResponse(
            content=[MockContentBlock("text", text="It is currently 12:00 PM in UTC.")],
            stop_reason="end_turn",
        ),
    ])

    registry = ToolRegistry()
    registry.register(DummyTimeTool())

    agent = AgentLoop(
        tool_registry=registry,
        client=mock_client,
        audit_logger=tmp_audit_logger,
    )

    result = agent.run(empty_memory)

    assert result.status == LoopStatus.COMPLETED
    assert "12:00 PM in UTC" in result.final_text
    assert result.iterations_used == 2
    assert len(mock_client.calls) == 2


def test_bad_arguments_error_recovery(empty_memory, tmp_audit_logger):
    """Test: Model passes invalid arguments, receives error, corrects arguments on next step."""
    empty_memory.add_user_message("What time is it?")

    mock_client = MockAnthropicClient([
        # Step 1: Model makes bad call (missing required 'timezone')
        MockResponse(
            content=[
                MockContentBlock(
                    "tool_use",
                    id="tool_bad_001",
                    name="get_time",
                    input_args={},  # Missing timezone!
                )
            ],
            stop_reason="tool_use",
        ),
        # Step 2: Model corrects argument after seeing validation error
        MockResponse(
            content=[
                MockContentBlock(
                    "tool_use",
                    id="tool_good_002",
                    name="get_time",
                    input_args={"timezone": "UTC"},
                )
            ],
            stop_reason="tool_use",
        ),
        # Step 3: Model answers
        MockResponse(
            content=[MockContentBlock("text", text="The time is 12:00 PM.")],
            stop_reason="end_turn",
        ),
    ])

    registry = ToolRegistry()
    registry.register(DummyTimeTool())

    agent = AgentLoop(
        tool_registry=registry,
        client=mock_client,
        audit_logger=tmp_audit_logger,
    )

    result = agent.run(empty_memory)

    assert result.status == LoopStatus.COMPLETED
    assert result.iterations_used == 3
    # Check that validation error was fed back into memory
    history = empty_memory.get_messages()
    assert any("Argument validation failed" in str(msg) for msg in history)


def test_approval_gate_pausing_and_resuming(empty_memory, tmp_audit_logger):
    """Test: A tool with risk_level='send' pauses at approval gate and resumes only upon confirmation."""
    from pydantic import BaseModel, Field

    class MockSendInput(BaseModel):
        file_id: str = Field(...)
        file_name: str = Field(...)

    class MockSendTool(Tool):
        name = "send_file"
        description = "Sends file to telegram"
        input_model = MockSendInput
        risk_level = "send"

        def run(self, args: MockSendInput) -> ToolResult:
            return ToolResult(
                success=True,
                data={"file_path": "/tmp/lecture.pdf", "file_name": args.file_name},
            )

    registry = ToolRegistry()
    registry.register(MockSendTool())

    mock_client = MockAnthropicClient([
        # Step 1: Model asks to send file
        MockResponse(
            content=[
                MockContentBlock(
                    "tool_use",
                    id="send_tool_1",
                    name="send_file",
                    input_args={"file_id": "file_123", "file_name": "OS_Notes.pdf"},
                )
            ],
            stop_reason="tool_use",
        ),
        # Step 2: After user approves, model receives confirmation and wraps up
        MockResponse(
            content=[MockContentBlock("text", text="I have sent OS_Notes.pdf to your chat!")],
            stop_reason="end_turn",
        ),
    ])

    agent = AgentLoop(
        tool_registry=registry,
        client=mock_client,
        audit_logger=tmp_audit_logger,
    )

    # 1. Initial run: should pause at approval gate
    result = agent.run(empty_memory)
    assert result.status == LoopStatus.AWAITING_APPROVAL
    assert result.pending_approval is not None
    assert result.pending_approval.tool_name == "send_file"
    assert "OS_Notes.pdf" in result.pending_approval.prompt_message

    # 2. Resuming with approval
    resume_payload = {
        "tool_use_id": result.pending_approval.tool_use_id,
        "tool_name": result.pending_approval.tool_name,
        "approved": True,
        "arguments": result.pending_approval.arguments,
    }

    resumed_result = agent.run(empty_memory, resume_approval=resume_payload)
    assert resumed_result.status == LoopStatus.COMPLETED
    assert "I have sent OS_Notes.pdf" in resumed_result.final_text
    assert resumed_result.file_to_send["file_path"] == "/tmp/lecture.pdf"


def test_max_iterations_cap(empty_memory, tmp_audit_logger):
    """Test: Agent loop stops and refuses runaway costs when hitting max_iterations."""
    # Loop that never ends: keeps requesting tool
    planned = [
        MockResponse(
            content=[
                MockContentBlock(
                    "tool_use",
                    id=f"tool_loop_{i}",
                    name="get_time",
                    input_args={"timezone": "UTC"},
                )
            ],
            stop_reason="tool_use",
        )
        for i in range(10)
    ]

    mock_client = MockAnthropicClient(planned)
    registry = ToolRegistry()
    registry.register(DummyTimeTool())

    agent = AgentLoop(
        tool_registry=registry,
        client=mock_client,
        max_iterations=6,
        audit_logger=tmp_audit_logger,
    )

    result = agent.run(empty_memory)
    assert result.status == LoopStatus.MAX_ITERATIONS_REACHED
    assert result.iterations_used == 6

