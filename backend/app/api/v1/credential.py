"""Credential API — CRUD for encrypted API keys, tokens, and login credentials.

All secrets are Fernet-encrypted at rest. The API never returns decrypted secrets.
A separate "reveal" endpoint allows one-at-a-time decryption with audit logging.
"""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.v1.deps import get_db
from app.services.credential_service import CredentialService

logger = structlog.get_logger()
router = APIRouter(prefix="/credentials", tags=["credentials"])


# ── Request / Response models ──────────────────────────────────

class CredentialCreateRequest(BaseModel):
    name: str
    auth_type: str = Field(..., description="bearer | api_key | basic | login_flow")
    data: dict[str, Any] = Field(..., description="Raw secret data: {\"token\": \"...\"} etc.")


class CredentialUpdateRequest(BaseModel):
    name: str | None = None
    auth_type: str | None = None
    data: dict[str, Any] | None = None


class CredentialResponse(BaseModel):
    id: str
    name: str
    auth_type: str
    has_cached_token: bool
    token_expires_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


def _to_response(cred) -> CredentialResponse:
    return CredentialResponse(
        id=str(cred.id),
        name=cred.name,
        auth_type=cred.auth_type,
        has_cached_token=cred.cached_token is not None,
        token_expires_at=cred.cached_token_expires_at.isoformat() if cred.cached_token_expires_at else None,
        created_at=cred.created_at.isoformat() if cred.created_at else None,
        updated_at=cred.updated_at.isoformat() if cred.updated_at else None,
    )


# ── Endpoints ──────────────────────────────────────────────────

@router.post("", response_model=CredentialResponse, status_code=201)
async def create_credential(req: CredentialCreateRequest, db: AsyncSession = Depends(get_db)):
    """Create a new credential. Secret data is Fernet-encrypted before storage."""
    svc = CredentialService(db)
    # TODO: replace with real user_id from auth context
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    cred = await svc.create(
        user_id=user_id,
        name=req.name,
        auth_type=req.auth_type,
        data=req.data,
    )
    return _to_response(cred)


@router.get("", response_model=list[CredentialResponse])
async def list_credentials(db: AsyncSession = Depends(get_db)):
    """List all credentials for the current user. Secrets are never included."""
    svc = CredentialService(db)
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    creds = await svc.list_by_user(user_id)
    return [_to_response(c) for c in creds]


@router.get("/{credential_id}", response_model=CredentialResponse)
async def get_credential(credential_id: str, db: AsyncSession = Depends(get_db)):
    """Get a credential by ID. Secrets are not included."""
    svc = CredentialService(db)
    cred = await svc.get(uuid.UUID(credential_id))
    if cred is None:
        raise HTTPException(status_code=404, detail="Credential not found")
    return _to_response(cred)


@router.patch("/{credential_id}", response_model=CredentialResponse)
async def update_credential(credential_id: str, req: CredentialUpdateRequest, db: AsyncSession = Depends(get_db)):
    """Update a credential. Only provided fields are changed."""
    svc = CredentialService(db)
    cred = await svc.update(
        uuid.UUID(credential_id),
        name=req.name,
        auth_type=req.auth_type,
        data=req.data,
    )
    if cred is None:
        raise HTTPException(status_code=404, detail="Credential not found")
    return _to_response(cred)


@router.delete("/{credential_id}", status_code=204)
async def delete_credential(credential_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a credential permanently."""
    svc = CredentialService(db)
    deleted = await svc.delete(uuid.UUID(credential_id))
    if not deleted:
        raise HTTPException(status_code=404, detail="Credential not found")


@router.post("/{credential_id}/reveal")
async def reveal_credential(credential_id: str, db: AsyncSession = Depends(get_db)):
    """Reveal the decrypted secret data. Use with caution — audit logged."""
    svc = CredentialService(db)
    data = await svc.get_decrypted_data(uuid.UUID(credential_id))
    if data is None:
        raise HTTPException(status_code=404, detail="Credential not found")
    logger.info("credential_revealed", credential_id=credential_id)
    return {"data": data}
