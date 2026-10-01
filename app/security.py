"""Small signed-session layer for the local portfolio demo.

This is intentionally self-contained so the app has no external identity-provider
dependency while learning locally. Production replaces demo login with OIDC.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from enum import StrEnum

from fastapi import Cookie, HTTPException, status


SESSION_COOKIE = "radar_session"
DEFAULT_SECRET = "local-development-only-change-me"


class Role(StrEnum):
    VIEWER = "viewer"
    APPROVER = "approver"
    OPERATOR = "operator"
    ADMIN = "admin"


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    role: Role

    def allows(self, *roles: Role) -> bool:
        return self.role is Role.ADMIN or self.role in roles


class SessionSigner:
    def __init__(self, secret: str | None = None) -> None:
        self.secret = (secret or os.getenv("APP_AUTH_SECRET") or DEFAULT_SECRET).encode()

    def issue(self, principal: Principal, ttl_seconds: int = 28_800) -> str:
        payload = {
            "sub": principal.user_id,
            "tenant": principal.tenant_id,
            "role": principal.role.value,
            "exp": int(time.time()) + ttl_seconds,
        }
        encoded = self._encode(payload)
        signature = hmac.new(self.secret, encoded.encode(), hashlib.sha256).hexdigest()
        return f"{encoded}.{signature}"

    def verify(self, token: str) -> Principal:
        try:
            encoded, provided_signature = token.rsplit(".", 1)
            expected_signature = hmac.new(self.secret, encoded.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(provided_signature, expected_signature):
                raise ValueError("Invalid signature")
            payload = json.loads(self._decode(encoded))
            if int(payload["exp"]) < time.time():
                raise ValueError("Expired session")
            return Principal(str(payload["sub"]), str(payload["tenant"]), Role(payload["role"]))
        except (KeyError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("Invalid session") from error

    @staticmethod
    def _encode(payload: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")

    @staticmethod
    def _decode(encoded: str) -> str:
        padded = encoded + "=" * (-len(encoded) % 4)
        return base64.urlsafe_b64decode(padded).decode()


signer = SessionSigner()


def current_principal(radar_session: str | None = Cookie(default=None)) -> Principal:
    if not radar_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in is required.")
    try:
        return signer.verify(radar_session)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is invalid or expired.") from error


def require_role(principal: Principal, *roles: Role) -> Principal:
    if not principal.allows(*roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your role is not allowed to perform this action.")
    return principal
