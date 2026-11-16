"""Tests for structured audit logging."""

import json
from edith.logging import AuditLogger


def test_structured_audit_logger(tmp_path):
    log_file = tmp_path / "test_audit.jsonl"
    logger = AuditLogger(log_path=str(log_file))

    # Log model call
    logger.log_model_call(
        model="claude-3-5-sonnet",
        messages_count=3,
        duration_ms=452.1,
        input_tokens=120,
        output_tokens=45,
        stop_reason="end_turn",
        tool_calls=[],
    )

    # Log tool call
    logger.log_tool_call(
        tool_name="search_drive",
        arguments={"query": "OS lecture"},
        risk_level="read",
        duration_ms=125.4,
        success=True,
        result_preview="Found 2 files",
    )

    # Log approval decision
    logger.log_approval(
        tool_name="send_file",
        arguments={"file_id": "xyz"},
        approved=True,
        user_id=123456789,
    )

    # Verify file was written
    assert log_file.exists()
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3

    # Parse and assert structure of records
    rec1 = json.loads(lines[0])
    assert rec1["event_type"] == "model_call"
    assert rec1["model"] == "claude-3-5-sonnet"
    assert rec1["input_tokens"] == 120
    assert rec1["output_tokens"] == 45

    rec2 = json.loads(lines[1])
    assert rec2["event_type"] == "tool_call"
    assert rec2["tool_name"] == "search_drive"
    assert rec2["risk_level"] == "read"
    assert rec2["success"] is True

    rec3 = json.loads(lines[2])
    assert rec3["event_type"] == "approval_decision"
    assert rec3["approved"] is True
