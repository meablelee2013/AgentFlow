#!/usr/bin/env python3
"""CLI tool to test api_call_node with any URL.

Usage:
    python scripts/test_api_call.py --url https://api.example.com/data
    python scripts/test_api_call.py --url https://api.example.com/post --method POST --body '{"key":"value"}'
    python scripts/test_api_call.py --url https://api.example.com/data --header "Authorization: Bearer token123"
    python scripts/test_api_call.py --url https://httpbin.org/json --response-path "slideshow.title"
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.engine.cs_nodes import api_call_node


def parse_headers(headers_list: list[str]) -> dict[str, str]:
    result = {}
    for h in headers_list:
        if ":" in h:
            key, value = h.split(":", 1)
            result[key.strip()] = value.strip()
    return result


async def main():
    parser = argparse.ArgumentParser(description="Test api_call_node with any URL")
    parser.add_argument("--url", required=True, help="Full URL to call")
    parser.add_argument(
        "--method", default="GET",
        choices=["GET", "POST", "PUT", "DELETE", "PATCH"],
    )
    parser.add_argument(
        "--header", action="append", default=[],
        help="HTTP header (format: 'Key: Value')",
    )
    parser.add_argument(
        "--query", action="append", default=[],
        help="Query param (format: 'key=value')",
    )
    parser.add_argument("--body", help="Request body (JSON string)")
    parser.add_argument(
        "--response-path",
        help="JSONPath to extract (e.g. 'data.items')",
    )
    parser.add_argument(
        "--timeout", type=int, default=30,
        help="Timeout in seconds",
    )

    args = parser.parse_args()

    # Parse query params
    query_params = {}
    for q in args.query:
        if "=" in q:
            key, value = q.split("=", 1)
            query_params[key.strip()] = value.strip()

    config = {
        "url": args.url,
        "method": args.method,
        "headers": parse_headers(args.header),
        "query_params": query_params,
        "body": args.body,
        "response_path": args.response_path,
        "timeout": args.timeout,
    }

    print(f"🔧 Calling: {args.method} {args.url}")
    print(f"📋 Config: {json.dumps(config, indent=2, ensure_ascii=False)}")
    print()

    result = await api_call_node(config)

    print(f"📡 Response:")
    print(f"   Status:   {result.get('status')}")
    print(f"   Duration: {result.get('duration_ms')}ms")
    if result.get("error"):
        print(f"   ❌ Error:  {result['error']}")
        sys.exit(1)
    else:
        print(f"   ✅ Success")
    print()
    print(f"   Body:")
    body = result.get("body")
    if body is not None:
        formatted = json.dumps(body, indent=2, ensure_ascii=False)
        if len(formatted) > 3000:
            print(formatted[:3000] + "\n   ... (truncated)")
        else:
            print(formatted)


if __name__ == "__main__":
    asyncio.run(main())