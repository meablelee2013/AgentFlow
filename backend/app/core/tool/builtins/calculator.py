"""Calculator tool — safe math expression evaluation."""
import math
from app.core.tool.base import BaseTool, ToolResult


class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Evaluate a mathematical expression. Supports +, -, *, /, **, sqrt, sin, cos, log, etc."
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Math expression to evaluate, e.g. '2 + 3 * 4' or 'sqrt(16)'",
            }
        },
        "required": ["expression"],
    }

    # Safe builtins for eval
    _SAFE_NAMES = {
        "abs": abs, "round": round, "min": min, "max": max,
        "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos,
        "tan": math.tan, "log": math.log, "log10": math.log10,
        "pi": math.pi, "e": math.e, "pow": pow, "ceil": math.ceil,
        "floor": math.floor, "int": int, "float": float,
    }

    async def execute(self, expression: str = "", **kwargs) -> ToolResult:
        try:
            # Evaluate with restricted builtins
            result = eval(expression, {"__builtins__": {}}, self._SAFE_NAMES)
            return ToolResult(success=True, output=str(result))
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
