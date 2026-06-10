"""CustomerServiceEngine node implementations.

This module contains all node handlers for the CustomerServiceEngine,
including the generic api_call_node and db_query_node infrastructure.
"""
import asyncio
import json
import time

import httpx


def _is_retryable(status_code: int | None, error: str | None) -> bool:
    """Check whether a request failure should be retried.

    Retry on: network errors, timeouts, 5xx server errors, 429 rate limits.
    Do NOT retry on: 4xx client errors (except 429).
    """
    if error:
        return True
    if status_code is None:
        return True
    return status_code >= 500 or status_code == 429


async def api_call_node(config: dict) -> dict:
    """Generic external API call utility with retry support.

    A standalone, reusable function for calling any external HTTP API.
    Used by all CustomerServiceEngine nodes that need external data.

    Args:
        config: API call configuration dict with schema:
            {
                "url": str,              # Required. Full URL.
                "method": str,           # GET/POST/PUT/DELETE/PATCH. Default: GET.
                "headers": dict,         # Optional HTTP headers.
                "query_params": dict,    # Optional query parameters.
                "body": str | dict,      # Optional request body (JSON string or dict).
                "response_path": str,    # Optional JSONPath to extract from response.
                "timeout": int,          # Seconds. Default: 30.
                "retry_count": int,      # Number of retries on failure. Default: 0.
            }

    Returns:
        {
            "status": int,              # HTTP status code
            "body": Any,                # Parsed response body
            "headers": dict,            # Response headers
            "duration_ms": int,         # Request duration
            "retries_used": int,        # Number of retries executed
            "error": str | None,        # Error message if failed
        }
    """
    url = config.get("url", "")
    method = config.get("method", "GET").upper()
    headers = dict(config.get("headers", {}))
    query_params = dict(config.get("query_params", {}))
    body = config.get("body")
    timeout = config.get("timeout", 30)
    retry_count = config.get("retry_count", 0)
    response_path = config.get("response_path", "")

    if not url:
        return {
            "status": None, "body": None, "headers": {},
            "duration_ms": 0, "retries_used": 0,
            "error": "URL is required",
        }

    # Convert dict body to JSON string
    if isinstance(body, dict):
        body = json.dumps(body, ensure_ascii=False)

    # ── Execute with retry ──────────────────────────────────
    total_duration_ms = 0
    retries_used = 0
    last_result = None

    for attempt in range(retry_count + 1):
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, trust_env=False) as client:
                resp = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=query_params,
                    content=body or None,
                )
            elapsed = int((time.monotonic() - start) * 1000)
            total_duration_ms += elapsed
            last_result = {"response": resp, "duration_ms": elapsed, "error": None}

            status = resp.status_code
            if not _is_retryable(status, None):
                break  # Success or non-retryable client error

        except httpx.TimeoutException:
            elapsed = int((time.monotonic() - start) * 1000)
            total_duration_ms += elapsed
            last_result = {"response": None, "duration_ms": elapsed,
                           "error": f"Request timed out after {timeout}s"}
        except httpx.RequestError as e:
            elapsed = int((time.monotonic() - start) * 1000)
            total_duration_ms += elapsed
            last_result = {"response": None, "duration_ms": elapsed,
                           "error": f"Request failed: {e}"}

        # Should we retry?
        current_status = last_result["response"].status_code if last_result["response"] else None
        current_error = last_result["error"]
        if not _is_retryable(current_status, current_error):
            break

        if attempt < retry_count:
            retries_used += 1
            backoff = 0.5 * (2 ** attempt)
            await asyncio.sleep(backoff)

    # ── Handle final error ──────────────────────────────────
    if last_result["error"]:
        return {
            "status": None, "body": None, "headers": {},
            "duration_ms": total_duration_ms, "retries_used": retries_used,
            "error": last_result["error"],
        }

    # ── Parse response body ─────────────────────────────────
    resp = last_result["response"]
    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            resp_body = resp.json()
        except Exception:
            resp_body = resp.text[:5000]
    else:
        resp_body = resp.text[:5000]

    # Extract specific path if configured
    if response_path and isinstance(resp_body, (dict, list)):
        from jsonpath_ng import parse as jsonpath_parse
        try:
            matches = [m.value for m in jsonpath_parse(f"$.{response_path}").find(resp_body)]
            if matches:
                resp_body = matches[0] if len(matches) == 1 else matches
        except Exception:
            pass

    return {
        "status": resp.status_code,
        "body": resp_body,
        "headers": dict(resp.headers),
        "duration_ms": total_duration_ms,
        "retries_used": retries_used,
        "error": None,
    }
