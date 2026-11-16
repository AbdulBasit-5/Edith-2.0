"""Structured JSON logging for EDITH 2.0 audit trail."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class AuditLogger:
    """Appends structured audit log events as JSON lines (JSONL)."""

    def __init__(self, log_path: str = "logs/edith.jsonl") -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._standard_logger = logging.getLogger("edith")

    def _write_record(self, record: Dict[str, Any]) -> None:
        try:
            line = json.dumps(record, default=str)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            self._standard_logger.error(f"Failed to write audit log record: {e}")

    def log_model_call(
        self,
        model: str,
        messages_count: int,
        duration_ms: float,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        stop_reason: Optional[str] = None,
        tool_calls: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Log a call to the LLM model."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "model_call",
            "model": model,
            "messages_count": messages_count,
            "duration_ms": round(duration_ms, 2),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "stop_reason": stop_reason,
            "tool_calls": tool_calls or [],
        }
        self._write_record(record)
        return record

    def log_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        risk_level: str,
        duration_ms: float,
        success: bool,
        error: Optional[str] = None,
        result_preview: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Log a tool execution event."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "tool_call",
            "tool_name": tool_name,
            "risk_level": risk_level,
            "arguments": arguments,
            "duration_ms": round(duration_ms, 2),
            "success": success,
            "error": error,
            "result_preview": result_preview,
        }
        self._write_record(record)
        return record

    def log_approval(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        approved: bool,
        user_id: int,
    ) -> Dict[str, Any]:
        """Log human-in-the-loop approval decision."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "approval_decision",
            "tool_name": tool_name,
            "arguments": arguments,
            "approved": approved,
            "user_id": user_id,
        }
        self._write_record(record)
        return record


# Global default audit logger
default_logger = AuditLogger()

