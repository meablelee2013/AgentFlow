"""DateTime tool — current time, date calculations."""
from datetime import datetime, timezone
from app.core.tool.base import BaseTool, ToolResult


class DateTimeTool(BaseTool):
    name = "datetime"
    description = "Get current date/time or convert between timezones."
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["now", "today", "timestamp"],
                "description": "What to get: 'now' (datetime), 'today' (date), 'timestamp' (unix)",
            }
        },
        "required": ["action"],
    }

    async def execute(self, action: str = "now", **kwargs) -> ToolResult:
        now = datetime.now(timezone.utc)
        if action == "now":
            return ToolResult(success=True, output=now.isoformat())
        elif action == "today":
            return ToolResult(success=True, output=now.strftime("%Y-%m-%d"))
        elif action == "timestamp":
            return ToolResult(success=True, output=str(int(now.timestamp())))
        return ToolResult(success=False, output="", error=f"Unknown action: {action}")
