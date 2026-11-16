"""Core ReAct agent loop with schema validation, error recovery, and approval gates."""

import time
from typing import Any, Dict, List, Optional
import anthropic

from edith.agent.state import (
    AgentStepResult,
    ConversationMemory,
    LoopStatus,
    PendingApproval,
)
from edith.logging import AuditLogger, default_logger
from edith.tools.base import ToolRegistry

DEFAULT_SYSTEM_PROMPT = """You are EDITH (Even Dead, I'm The Hero), a sharp, responsive, daily task-driven AI companion.
You assist your user directly from Telegram.

Guidelines:
1. When asked to find a file or lecture notes, use the `search_drive` tool first.
2. Present the search results clearly (file name, ID, modified date).
3. If the user wants you to send the file to their chat, use the `send_file` tool.
   (Note: `send_file` will automatically ask the user for confirmation via interactive buttons).
4. Keep your conversational responses concise, clear, and action-oriented.
"""


class AgentLoop:
    """Manages multi-turn ReAct reasoning, tool execution, and approval pausing."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        client: Optional[anthropic.Anthropic] = None,
        api_key: Optional[str] = None,
        model: str = "claude-3-5-sonnet-20241022",
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_iterations: int = 6,
        audit_logger: Optional[AuditLogger] = None,
    ) -> None:
        self.tool_registry = tool_registry
        self.model = model
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        self.logger = audit_logger or default_logger

        if client is not None:
            self.client = client
        elif api_key:
            self.client = anthropic.Anthropic(api_key=api_key)
        else:
            self.client = None  # Mock or lazy initialized

    def run(
        self,
        memory: ConversationMemory,
        resume_approval: Optional[Dict[str, Any]] = None,
    ) -> AgentStepResult:
        """Run the agent loop until completion or until approval is required.

        Args:
            memory: The conversation memory holding messages for this chat.
            resume_approval: If resuming after an approval decision, contains:
                {"tool_use_id": str, "tool_name": str, "approved": bool, "arguments": dict}
        """
        if not self.client:
            return AgentStepResult(
                status=LoopStatus.ERROR,
                error_message="Anthropic API client is not configured.",
            )

        tools_schema = self.tool_registry.get_all_schemas()
        iterations = 0
        total_in_tokens = 0
        total_out_tokens = 0
        file_ready_to_send = None

        # Handle resumed approval if provided
        if resume_approval:
            tool_id = resume_approval["tool_use_id"]
            tool_name = resume_approval["tool_name"]
            approved = resume_approval["approved"]
            args = resume_approval.get("arguments", {})

            if approved:
                tool = self.tool_registry.get(tool_name)
                start_t = time.perf_counter()
                tool_result = tool.validate_and_run(args)
                dur_ms = (time.perf_counter() - start_t) * 1000

                self.logger.log_tool_call(
                    tool_name=tool_name,
                    arguments=args,
                    risk_level=tool.risk_level if tool else "send",
                    duration_ms=dur_ms,
                    success=tool_result.success,
                    error=tool_result.error,
                    result_preview=tool_result.to_content()[:200],
                )

                if tool_result.success and isinstance(tool_result.data, dict) and tool_result.data.get("file_path"):
                    file_ready_to_send = tool_result.data

                memory.add_tool_result(tool_id, tool_result.to_content())
            else:
                memory.add_tool_result(tool_id, "User declined the request to send this file.")

        while iterations < self.max_iterations:
            iterations += 1
            messages = memory.get_messages()

            start_time = time.perf_counter()
            response = self.client.messages.create(
                model=self.model,
                system=self.system_prompt,
                messages=messages,
                tools=tools_schema if tools_schema else None,
                max_tokens=1024,
            )
            duration_ms = (time.perf_counter() - start_time) * 1000

            in_tokens = getattr(response.usage, "input_tokens", 0)
            out_tokens = getattr(response.usage, "output_tokens", 0)
            total_in_tokens += in_tokens
            total_out_tokens += out_tokens

            # Extract tool calls from response
            tool_calls = [
                {"id": block.id, "name": block.name, "input": block.input}
                for block in response.content
                if block.type == "tool_use"
            ]

            self.logger.log_model_call(
                model=self.model,
                messages_count=len(messages),
                duration_ms=duration_ms,
                input_tokens=in_tokens,
                output_tokens=out_tokens,
                stop_reason=response.stop_reason,
                tool_calls=tool_calls,
            )

            # Add assistant message to history
            memory.add_assistant_message(response.content)

            # If model answered in text without requesting tools
            if response.stop_reason == "end_turn" or not tool_calls:
                text_blocks = [b.text for b in response.content if hasattr(b, "text")]
                final_text = "\n".join(text_blocks).strip()
                return AgentStepResult(
                    status=LoopStatus.COMPLETED,
                    final_text=final_text,
                    iterations_used=iterations,
                    total_input_tokens=total_in_tokens,
                    total_output_tokens=total_out_tokens,
                    file_to_send=file_ready_to_send,
                )

            # Process tool calls
            for tool_use in tool_calls:
                t_name = tool_use["name"]
                t_id = tool_use["id"]
                t_args = tool_use["input"]

                # Check if approval is required for this tool
                if self.tool_registry.is_risk_send(t_name):
                    fname = t_args.get("file_name", "the requested file")
                    prompt_msg = f"EDITH wants to send *{fname}* to your Telegram chat.\nDo you approve?"
                    return AgentStepResult(
                        status=LoopStatus.AWAITING_APPROVAL,
                        pending_approval=PendingApproval(
                            tool_use_id=t_id,
                            tool_name=t_name,
                            arguments=t_args,
                            prompt_message=prompt_msg,
                        ),
                        iterations_used=iterations,
                        total_input_tokens=total_in_tokens,
                        total_output_tokens=total_out_tokens,
                    )

                # Read tool: run immediately
                tool = self.tool_registry.get(t_name)
                if not tool:
                    err_msg = f"Error: Tool '{t_name}' not found in registry."
                    memory.add_tool_result(t_id, err_msg)
                    continue

                tool_start = time.perf_counter()
                tool_res = tool.validate_and_run(t_args)
                tool_dur = (time.perf_counter() - tool_start) * 1000

                self.logger.log_tool_call(
                    tool_name=t_name,
                    arguments=t_args,
                    risk_level=tool.risk_level,
                    duration_ms=tool_dur,
                    success=tool_res.success,
                    error=tool_res.error,
                    result_preview=tool_res.to_content()[:200],
                )

                # Feed result back into loop
                memory.add_tool_result(t_id, tool_res.to_content())

        return AgentStepResult(
            status=LoopStatus.MAX_ITERATIONS_REACHED,
            final_text="I reached the maximum iterations limit (6) while processing your request.",
            iterations_used=iterations,
            total_input_tokens=total_in_tokens,
            total_output_tokens=total_out_tokens,
        )
