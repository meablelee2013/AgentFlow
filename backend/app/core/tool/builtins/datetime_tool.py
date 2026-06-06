"""DateTime tool — LangChain BaseTool for native function calling."""
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool


class DateTimeInput(BaseModel):
    action: str = Field(
        default="now",
        description="What to get: 'now' (datetime), 'today' (date), 'timestamp' (unix)",
    )


class DateTimeTool(BaseTool):
    name: str = "datetime"
    description: str = "Get current date/time or unix timestamp."
    args_schema: type[BaseModel] = DateTimeInput

    async def _arun(self, action: str = "now") -> str:
        now = datetime.now(timezone.utc)
        if action == "now":
            return now.isoformat()
        elif action == "today":
            return now.strftime("%Y-%m-%d")
        elif action == "timestamp":
            return str(int(now.timestamp()))
        return f"Unknown action: {action}. Use 'now', 'today', or 'timestamp'."

    def _run(self, action: str = "now") -> str:
        raise NotImplementedError("Use _arun (async)")
