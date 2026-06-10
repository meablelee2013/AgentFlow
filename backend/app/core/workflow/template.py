"""
Template resolver — Coze-style variable interpolation for workflow nodes.

Supports:
    {{input.query}}              — start node global input
    {{sys.user_id}}              — system variables
    {{node_1.body.items[0].name}} — upstream node output (with JSONPath)

Usage:
    from app.core.workflow.template import resolve_template

    result = resolve_template(
        "Hello {{input.name}}, your repos: {{node_1.body.items[0].name}}",
        state
    )
"""

import json
import re
from typing import Any

from jsonpath_ng import parse as jsonpath_parse

# Pattern: {{ variable.expression }}
VAR_PATTERN = re.compile(r'\{\{\s*([^}]+?)\s*\}\}')


def resolve_template(template: str, state: dict) -> Any:
    """Resolve all {{...}} variables in a template string.

    Args:
        template: String containing {{var}} placeholders
        state: LangGraph state dict with "node_outputs" key

    Returns:
        String with all variables replaced by their values.
        If the entire template is a single variable, returns the raw value
        (preserving dict/list types instead of JSON-stringifying them).
    """
    if not template or "{{" not in template:
        return template

    node_outputs = state.get("node_outputs", {})
    sys_vars = state.get("sys", {})

    # If the entire template is a single variable reference like "{{node_1.body}}"
    # return the raw value (not stringified) so downstream code gets the real type.
    single_match = re.fullmatch(r'\s*\{\{\s*([^}]+?)\s*\}\}\s*', template)
    if single_match:
        return _resolve_var(single_match.group(1), node_outputs, sys_vars)

    # Mixed template — replace each {{...}} with stringified value
    def replacer(match: re.Match) -> str:
        expr = match.group(1)
        value = _resolve_var(expr, node_outputs, sys_vars)
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    return VAR_PATTERN.sub(replacer, template)


def _resolve_var(expr: str, node_outputs: dict, sys_vars: dict) -> Any:
    """Resolve a single variable expression.

    Handles:
      - input.xxx        → node_outputs["start"]["xxx"] (or node_outputs["input"])
      - sys.xxx          → sys_vars["xxx"]
      - node_id.field... → node_outputs["node_id"]["field"]... (JSONPath)
    """
    expr = expr.strip()

    # System variables: {{sys.user_id}}
    if expr.startswith("sys."):
        key = expr[4:]
        return sys_vars.get(key)

    # Start node input: {{input.query}}
    # Maps to node_outputs["start"] or node_outputs["input"]
    if expr.startswith("input."):
        key = expr[6:]
        input_data = node_outputs.get("start", node_outputs.get("input", {}))
        return _extract_path(input_data, key)

    # Upstream node reference: {{node_1.body.items[0].name}}
    parts = expr.split('.', 1)
    node_id = parts[0]
    path = parts[1] if len(parts) > 1 else ""

    node_data = node_outputs.get(node_id)
    if node_data is None:
        return None

    if not path:
        return node_data

    return _extract_path(node_data, path)


def _extract_path(data: Any, path: str) -> Any:
    """Extract a value from data using a dot/bracket path.

    Supports:
      - body.items           → data["body"]["items"]
      - body.items[0]        → data["body"]["items"][0]
      - body.items[0].name   → data["body"]["items"][0]["name"]

    Uses jsonpath-ng for robust parsing of mixed dot/bracket expressions.
    """
    if not data or not path:
        return data

    try:
        jsonpath = jsonpath_parse(f"$.{path}")
        matches = [m.value for m in jsonpath.find(data)]
        return matches[0] if matches else None
    except Exception:
        return None


def resolve_inputs(inputs: list, state: dict) -> dict[str, Any]:
    """Resolve all input parameter declarations into a concrete args dict.

    This is the Coze-style input resolution:
    each NodeIOParam has source="reference" (with a ref) or source="literal" (with a value).

    Args:
        inputs: List of NodeIOParam objects
        state: LangGraph state dict

    Returns:
        Dict mapping param name → resolved value
    """
    args = {}
    for param in inputs:
        if param.source == "literal":
            args[param.name] = param.value
        elif param.source == "reference" and param.ref:
            args[param.name] = _resolve_var(
                param.ref,
                state.get("node_outputs", {}),
                state.get("sys", {}),
            )
    return args
