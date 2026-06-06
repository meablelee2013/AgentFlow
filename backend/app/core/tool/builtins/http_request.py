"""HTTP Request tool — make API calls from within agent workflows."""
import httpx
from app.core.tool.base import BaseTool, ToolResult


class HTTPRequestTool(BaseTool):
    name = "http_request"
    description = "Make an HTTP request to an external API. Returns response body."
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to request",
            },
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "DELETE"],
                "description": "HTTP method",
            },
        },
        "required": ["url"],
    }

    async def execute(self, url: str = "", method: str = "GET", **kwargs) -> ToolResult:
        if not url.startswith(("http://", "https://")):
            return ToolResult(success=False, output="", error="URL must start with http:// or https://")

        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                if method == "GET":
                    resp = await client.get(url)
                elif method == "POST":
                    resp = await client.post(url)
                elif method == "PUT":
                    resp = await client.put(url)
                elif method == "DELETE":
                    resp = await client.delete(url)
                else:
                    return ToolResult(success=False, output="", error=f"Unsupported method: {method}")

                # Truncate long responses
                body = resp.text[:2000]
                return ToolResult(
                    success=True,
                    output=f"Status {resp.status_code}\n{body}",
                    metadata={"status_code": resp.status_code},
                )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
