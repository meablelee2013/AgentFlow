"""
BaseTool — abstract tool interface for the agent tool system.

Design pattern: **Command Pattern**
    Each tool encapsulates a single action with a defined schema.
    The agent invokes tools via LLM function calling, using the
    schema to validate arguments.

```mermaid
classDiagram
    class BaseTool {
        <<abstract>>
        +name: str
        +description: str
        +parameters: dict  (JSON Schema)
        +execute(kwargs) ToolResult
    }
    class CalculatorTool { +execute() }
    class DateTimeTool { +execute() }
    class WebSearchTool { +execute() }
    class HTTPRequestTool { +execute() }
    BaseTool <|-- CalculatorTool
    BaseTool <|-- DateTimeTool
    BaseTool <|-- WebSearchTool
    BaseTool <|-- HTTPRequestTool
```
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ToolResult:
    """Result returned by a tool execution."""
    success: bool
    output: str
    error: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_llm_message(self) -> str:
        """Format result for LLM consumption."""
        if self.success:
            return self.output
        return f"Error: {self.error}"


class BaseTool(ABC):
    """Abstract tool — every tool must implement this interface.

    Usage:
        class MyTool(BaseTool):
            name = "my_tool"
            description = "Does something useful"
            parameters = {
                "type": "object",
                "properties": {
                    "arg1": {"type": "string", "description": "First argument"}
                },
                "required": ["arg1"]
            }

            async def execute(self, **kwargs) -> ToolResult:
                return ToolResult(success=True, output=f"Got: {kwargs['arg1']}")
    """

    name: str = ""
    description: str = ""
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {},
        "required": [],
    })

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given arguments. Returns a ToolResult."""
        ...

    def to_openai_schema(self) -> dict:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
