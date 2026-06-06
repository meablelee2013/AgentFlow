"""Calculator tool — inherits LangChain's BaseTool for native function calling."""
import math
from typing import Any
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool


class CalculatorInput(BaseModel):
    """Input schema for calculator — auto-generated as JSON Schema for LLM."""
    expression: str = Field(
        description="Math expression to evaluate, e.g. '2 + 3 * 4' or 'sqrt(144)'"
    )


class CalculatorTool(BaseTool):
    name: str = "calculator"
    description: str = "Evaluate a mathematical expression. Supports +, -, *, /, **, sqrt, sin, cos, log, etc."
    args_schema: type[BaseModel] = CalculatorInput

    _SAFE_NAMES: dict[str, Any] = {
        "abs": abs, "round": round, "min": min, "max": max,
        "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos,
        "tan": math.tan, "log": math.log, "log10": math.log10,
        "pi": math.pi, "e": math.e, "pow": pow, "ceil": math.ceil,
        "floor": math.floor, "int": int, "float": float,
    }

    async def _arun(self, expression: str = "") -> str:
        try:
            result = eval(expression, {"__builtins__": {}}, self._SAFE_NAMES)
            return str(result)
        except Exception as e:
            return f"Error: {e}"

    def _run(self, expression: str = "") -> str:
        raise NotImplementedError("Use _arun (async)")
