"""Credential model — encrypted storage for API keys, tokens, and login credentials.

Encryption: Fernet (symmetric, AES-128-CBC) via cryptography.fernet.
Key stored in settings.ENCRYPTION_KEY.

Supported auth types:
    - bearer:       {"token": "ghp_xxx"}
    - api_key:      {"key": "abc123"}
    - basic:        {"username": "u", "password": "p"}
    - login_flow:   {"username": "u", "password": "p"}
"""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class Credential(Base):
    """Encrypted credential for external API / database / system access.

    Node configs only reference credential_id — never store plaintext keys in workflows.
    """

    __tablename__ = "credentials"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="Human-readable label, e.g. 'GitHub Token', 'Company ERP'"
    )
    auth_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
        comment="bearer | api_key | basic | login_flow"
    )
    encrypted_data: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="Fernet-encrypted JSON blob holding the actual secrets"
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False,
        comment="Owning user — client-side UUID (future: FK → users.id)"
    )

    # ── login_flow token cache ──
    cached_token: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Fernet-encrypted cached access token (login_flow only)"
    )
    cached_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="When the cached token expires"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
