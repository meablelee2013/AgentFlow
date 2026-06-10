"""CredentialService — encrypted credential storage, token caching, auto-refresh.

Encryption:
    Fernet (AES-128-CBC via cryptography.fernet) with key from settings.ENCRYPTION_KEY.
    All secrets are encrypted at rest — node configs only reference credential_id.

Login flow auto-refresh:
    For auth_type="login_flow": cached token is used until expiry, then
    force_relogin() is called to obtain a fresh token.
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.credential import Credential


def _get_fernet() -> Fernet | None:
    """Return a Fernet instance if ENCRYPTION_KEY is configured.

    If the key is empty (default), credentials cannot be encrypted/decrypted
    and the service will raise a clear error.
    """
    key = settings.ENCRYPTION_KEY
    if not key:
        return None
    return Fernet(key.encode() if isinstance(key, str) else key)


class CredentialService:
    """CRUD + token lifecycle for credentials."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Encryption helpers ──────────────────────────────────

    @staticmethod
    def _encrypt(data: dict[str, Any]) -> str:
        f = _get_fernet()
        if f is None:
            raise RuntimeError("ENCRYPTION_KEY is not configured — cannot encrypt credentials.")
        return f.encrypt(json.dumps(data).encode()).decode()

    @staticmethod
    def _decrypt(encrypted: str) -> dict[str, Any]:
        f = _get_fernet()
        if f is None:
            raise RuntimeError("ENCRYPTION_KEY is not configured — cannot decrypt credentials.")
        return json.loads(f.decrypt(encrypted.encode()))

    # ── CRUD ────────────────────────────────────────────────

    async def create(
        self,
        user_id: uuid.UUID,
        name: str,
        auth_type: str,
        data: dict[str, Any],
    ) -> Credential:
        """Create a new credential. `data` is the raw secret dict (e.g. {"token": "ghp_xxx"})."""
        credential = Credential(
            name=name,
            auth_type=auth_type,
            encrypted_data=self._encrypt(data),
            user_id=user_id,
        )
        self.db.add(credential)
        await self.db.commit()
        await self.db.refresh(credential)
        return credential

    async def get(self, credential_id: uuid.UUID, user_id: uuid.UUID | None = None) -> Credential | None:
        """Get a credential by ID, optionally scoped to a user."""
        stmt = select(Credential).where(Credential.id == credential_id)
        if user_id:
            stmt = stmt.where(Credential.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: uuid.UUID) -> list[Credential]:
        """List all credentials for a user (never returns decrypted secrets)."""
        result = await self.db.execute(
            select(Credential).where(Credential.user_id == user_id).order_by(Credential.updated_at.desc())
        )
        return list(result.scalars().all())

    async def update(
        self,
        credential_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        *,
        name: str | None = None,
        auth_type: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> Credential | None:
        """Update credential fields. Only provided fields are changed."""
        cred = await self.get(credential_id, user_id)
        if cred is None:
            return None
        if name is not None:
            cred.name = name
        if auth_type is not None:
            cred.auth_type = auth_type
            # Clear cached token on auth_type change
            cred.cached_token = None
            cred.cached_token_expires_at = None
        if data is not None:
            cred.encrypted_data = self._encrypt(data)
            # Clear cached token when secrets change
            cred.cached_token = None
            cred.cached_token_expires_at = None
        await self.db.commit()
        await self.db.refresh(cred)
        return cred

    async def delete(self, credential_id: uuid.UUID, user_id: uuid.UUID | None = None) -> bool:
        """Delete a credential. Returns True if deleted, False if not found."""
        stmt = delete(Credential).where(Credential.id == credential_id)
        if user_id:
            stmt = stmt.where(Credential.user_id == user_id)
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0

    # ── Secret access ───────────────────────────────────────

    async def get_decrypted_data(self, credential_id: uuid.UUID) -> dict[str, Any] | None:
        """Get the decrypted secret data for a credential. Use sparingly."""
        cred = await self.get(credential_id)
        if cred is None:
            return None
        return self._decrypt(cred.encrypted_data)

    # ── Token lifecycle (login_flow) ────────────────────────

    async def get_or_refresh_token(
        self,
        credential_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> str:
        """Get a valid access token — refresh if expired or missing.

        For auth_type != "login_flow", simply returns the stored secret/token.
        For login_flow: checks cached token expiry, refreshes if needed.
        """
        cred = await self.get(credential_id, user_id)
        if cred is None:
            raise ValueError(f"Credential {credential_id} not found")

        if cred.auth_type != "login_flow":
            # For bearer/api_key/basic — just return the raw secret
            data = self._decrypt(cred.encrypted_data)
            return data.get("token", data.get("key", data.get("password", "")))

        # login_flow: check cached token
        if cred.cached_token and cred.cached_token_expires_at:
            now = datetime.now(timezone.utc)
            # Refresh if expiring within 60 seconds
            if cred.cached_token_expires_at > now and \
               (cred.cached_token_expires_at - now).total_seconds() > 60:
                return self._decrypt(cred.cached_token).get("token", "")

        # Token expired or missing — refresh
        return await self.force_relogin(credential_id, user_id)

    async def force_relogin(
        self,
        credential_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> str:
        """Force a login to obtain a fresh token (login_flow only).

        Posts to login_url with login_body, extracts token via JSONPath,
        caches it encrypted with TTL.
        """
        cred = await self.get(credential_id, user_id)
        if cred is None:
            raise ValueError(f"Credential {credential_id} not found")

        if cred.auth_type != "login_flow":
            raise ValueError("force_relogin is only for login_flow credentials")

        data = self._decrypt(cred.encrypted_data)

        # Login request
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method=data.get("login_method", "POST"),
                url=data["login_url"],
                content=data.get("login_body", ""),
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            resp_data = resp.json()

        # Extract token via JSONPath
        token_path = data.get("token_path", "$.data.token")
        from jsonpath_ng import parse as jsonpath_parse
        try:
            matches = [m.value for m in jsonpath_parse(token_path).find(resp_data)]
            token = str(matches[0]) if matches else ""
        except Exception:
            token = ""

        if not token:
            raise ValueError(f"Could not extract token from login response using path: {token_path}")

        # Cache token
        from datetime import timedelta
        ttl = data.get("token_ttl", 3600)
        cred.cached_token = self._encrypt({"token": token})
        cred.cached_token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        await self.db.commit()

        return token
