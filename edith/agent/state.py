"""Agent state representation and sliding window conversation history."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class LoopStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    MAX_ITERATIONS_REACHED = "max_iterations_reached"
    ERROR = "error"


class PendingApproval(BaseModel):
    """Details of a tool call waiting for human confirmation."""

    tool_use_id: str
    tool_name: str
    arguments: Dict[str, Any]
    prompt_message: str


class AgentStepResult(BaseModel):
    """Result of running the agent loop."""

    status: LoopStatus
    final_text: Optional[str] = None
    pending_approval: Optional[PendingApproval] = None
    error_message: Optional[str] = None
    iterations_used: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    file_to_send: Optional[Dict[str, Any]] = None


class ConversationMemory:
    """Sliding-window conversational memory per chat."""

    def __init__(self, max_turns: int = 10) -> None:
        self.max_turns = max_turns
        self.messages: List[Dict[str, Any]] = []

    def add_user_message(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})
        self._trim()

    def add_assistant_message(self, content: Any) -> None:
        self.messages.append({"role": "assistant", "content": content})
        self._trim()

    def add_tool_result(self, tool_use_id: str, content: str) -> None:
        self.messages.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": content,
                }
            ],
        })
        self._trim()

    def get_messages(self) -> List[Dict[str, Any]]:
        return list(self.messages)

    def _trim(self) -> None:
        # Keep last max_turns * 2 messages (pairs of user/assistant)
        limit = self.max_turns * 2
        if len(self.messages) > limit:
            self.messages = self.messages[-limit:]
            # Ensure the trimmed slice starts with a user message for Anthropic API validity
            while self.messages and self.messages[0].get("role") != "user":
                self.messages.pop(0)

    def clear(self) -> None:
        self.messages.clear()
