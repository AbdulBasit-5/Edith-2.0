"""Base tool abstraction and registry with Pydantic validation and risk tiers."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Literal, Optional, Type
from pydantic import BaseModel, ValidationError

RiskLevel = Literal["read", "send"]


class ToolResult(BaseModel):
    """Standardized output from a tool run."""

    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None

    def to_content(self) -> str:
        """Serialize result to a readable string for the LLM."""
        if self.success:
            if isinstance(self.data, str):
                return self.data
            import json

            return json.dumps(self.data, indent=2, default=str)
        return f"Tool Execution Error: {self.error}"


class Tool(ABC):
    """Abstract Base Class for all EDITH agent tools."""

    name: str
    description: str
    input_model: Type[BaseModel]
    risk_level: RiskLevel = "read"

    def to_anthropic_schema(self) -> Dict[str, Any]:
        """Generate the Anthropic tool definition using Pydantic's JSON schema."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
        }

    def validate_and_run(self, raw_args: Dict[str, Any]) -> ToolResult:
        """Validate input arguments against input_model and run the tool."""
        try:
            validated = self.input_model.model_validate(raw_args)
        except ValidationError as e:
            return ToolResult(
                success=False,
                error=f"Argument validation failed: {e.errors()}",
            )

        try:
            return self.run(validated)
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Internal error executing {self.name}: {str(e)}",
            )

    @abstractmethod
    def run(self, args: Any) -> ToolResult:
        """Execute the tool logic with validated arguments."""
        pass


class ToolRegistry:
    """Registry maintaining available tools for the agent."""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """Retrieve a tool by name."""
        return self._tools.get(name)

    def get_all_schemas(self) -> list[Dict[str, Any]]:
        """Return Anthropic schemas for all registered tools."""
        return [tool.to_anthropic_schema() for tool in self._tools.values()]

    def is_risk_send(self, name: str) -> bool:
        """Check if a tool requires approval before execution."""
        tool = self._tools.get(name)
        return tool.risk_level == "send" if tool else False
