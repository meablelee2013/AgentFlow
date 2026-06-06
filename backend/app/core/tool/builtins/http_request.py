"""HTTP Request tool — LangChain BaseTool, calls external APIs."""
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool


class HTTPRequestInput(BaseModel):
    url: str = Field(description="The URL to request (must start with http:// or https://)")
    method: str = Field(default="GET", description="HTTP method: GET, POST, PUT, DELETE")


class HTTPRequestTool(BaseTool):
    name: str = "http_request"
    description: str = "Make an HTTP request to an external API. Returns response body (truncated to 2000 chars)."
    args_schema: type[BaseModel] = HTTPRequestInput

    async def _arun(self, url: str = "", method: str = "GET") -> str:
        if not url.startswith(("http://", "https://")):
            return "Error: URL must start with http:// or https://"

        import httpx
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
                    return f"Error: unsupported method '{method}'"
                return f"Status {resp.status_code}\n{resp.text[:2000]}"
        except Exception as e:
            return f"Error: {e}"

    def _run(self, url: str = "", method: str = "GET") -> str:
        raise NotImplementedError("Use _arun (async)")
