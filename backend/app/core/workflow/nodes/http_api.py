"""HTTP API node executor — call external APIs with authentication.

Supports: none, bearer, api_key, basic, login_flow (enterprise internal systems).
Includes automatic retry on failure with configurable retry_count.

Credential integration:
    When credential_id is set, the executor fetches and decrypts the secret
    from the credentials table via CredentialService.
"""
import base64
import asyncio
import time
import uuid
from typing import Any

import httpx

from app.api.v1.deps import AsyncSessionLocal
from app.services.credential_service import CredentialService


async def _execute_request(
    url: str, method: str, headers: dict, query_params: dict,
    body: str | None, timeout: int,
) -> dict:
    """Execute a single HTTP request. Returns result dict."""
    start = time.monotonic()
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        resp = await client.request(
            method=method,
            url=url,
            headers=headers,
            params=query_params,
            content=body or None,
        )
        elapsed = int((time.monotonic() - start) * 1000)
    return {"response": resp, "duration_ms": elapsed, "error": None}


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


async def http_api_handler(args: dict, config: dict, state: dict) -> dict:
    """Execute an HTTP API request with retry support.

    Args:
        args: Resolved input parameters from upstream nodes
        config: Node configuration (HTTPAPINodeData fields)
        state: LangGraph state (ChatState)

    Returns:
        Structured output dict with status, body, headers, duration_ms, retries_used.
    """
    url = config.get("url", "")
    method = config.get("method", "GET")
    headers = dict(config.get("headers", {}))
    query_params = dict(config.get("query_params", {}))
    body = config.get("body", "")
    timeout = config.get("timeout", 30)
    retry_count = config.get("retry_count", 0)

    # Replace URL template variables with args
    for key, val in args.items():
        url = url.replace(f"{{{key}}}", str(val))

    # ── Authentication ──────────────────────────────────────
    auth_mode = config.get("auth_mode", "none")
    credential_id = config.get("credential_id", "")

    if auth_mode != "none" and credential_id:
        try:
            cid = uuid.UUID(credential_id)
        except (ValueError, TypeError):
            cid = None

        if cid:
            async with AsyncSessionLocal() as db:
                svc = CredentialService(db)
                token = await svc.get_or_refresh_token(cid)

                if auth_mode == "bearer":
                    headers["Authorization"] = f"Bearer {token}"
                elif auth_mode == "api_key":
                    api_key_location = config.get("api_key_location", "header")
                    api_key_name = config.get("api_key_name", "X-API-Key")
                    if api_key_location == "header":
                        headers[api_key_name] = token
                    else:
                        query_params[api_key_name] = token
                elif auth_mode == "basic":
                    data = await svc.get_decrypted_data(cid)
                    if data:
                        username = data.get("username", "")
                        password = data.get("password", token)
                        encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
                        headers["Authorization"] = f"Basic {encoded}"

    # ── Execute with retry ──────────────────────────────────
    total_duration_ms = 0
    retries_used = 0
    last_result = None

    for attempt in range(retry_count + 1):
        result = await _execute_request(url, method, headers, query_params, body, timeout)
        total_duration_ms += result["duration_ms"]
        last_result = result

        if result["error"] is None:
            resp = result["response"]
            status = resp.status_code

            # 401 retry for login_flow (this is a special auth retry, separate from failure retry)
            if status == 401 and auth_mode == "login_flow" and credential_id:
                try:
                    cid = uuid.UUID(credential_id)
                except (ValueError, TypeError):
                    cid = None
                if cid:
                    async with AsyncSessionLocal() as db:
                        svc = CredentialService(db)
                        token = await svc.force_relogin(cid)
                        token_header_format = config.get("token_header_format", "Bearer {token}")
                        headers[config.get("token_header_name", "Authorization")] = \
                            token_header_format.format(token=token)
                    # Retry with refreshed token (don't count against retry_count)
                    continue

            if not _is_retryable(status, result["error"]):
                break  # Success or non-retryable error — don't retry

        if attempt < retry_count:
            retries_used += 1
            # Exponential backoff: 500ms, 1s, 2s, 4s...
            backoff = 0.5 * (2 ** (attempt - 1)) if attempt > 0 else 0.5
            await asyncio.sleep(backoff)

    # ── Parse response ──────────────────────────────────────
    resp = last_result["response"]
    try:
        resp_body = resp.json()
    except Exception:
        resp_body = resp.text[:2000]

    # Extract specific path if configured
    response_path = config.get("response_path", "")
    if response_path and isinstance(resp_body, (dict, list)):
        from jsonpath_ng import parse as jsonpath_parse
        try:
            matches = [m.value for m in jsonpath_parse(f"$.{response_path}").find(resp_body)]
            if matches:
                resp_body = matches[0] if len(matches) == 1 else matches
        except Exception:
            pass  # Keep full body if JSONPath fails

    return {
        "status": resp.status_code,
        "body": resp_body,
        "headers": dict(resp.headers),
        "duration_ms": total_duration_ms,
        "retries_used": retries_used,
    }
