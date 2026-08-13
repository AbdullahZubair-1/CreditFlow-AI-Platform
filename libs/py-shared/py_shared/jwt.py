"""RS256 JWT encode/decode helpers shared by every CreditFlow service.

The Auth Service holds the private key and issues tokens; every other
service (starting with the Gateway) only ever needs the public key to
verify them. Both keys are loaded from environment-provided PEM strings
so the same code works whether running via docker-compose or in CI.
"""
from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

import jwt

ALGORITHM = "RS256"
ACCESS_TOKEN_TTL_SECONDS = 15 * 60
REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60


@dataclass(frozen=True)
class TokenClaims:
    user_id: str
    account_id: str
    role: str
    jti: str
    exp: int


def _load_key(env_var: str) -> str:
    value = os.environ.get(env_var)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {env_var}")
    return value.replace("\\n", "\n")


def get_private_key() -> str:
    return _load_key("JWT_PRIVATE_KEY")


def get_public_key() -> str:
    return _load_key("JWT_PUBLIC_KEY")


def issue_access_token(user_id: str, account_id: str, role: str) -> tuple[str, TokenClaims]:
    jti = str(uuid.uuid4())
    exp = int(time.time()) + ACCESS_TOKEN_TTL_SECONDS
    claims = TokenClaims(user_id=user_id, account_id=account_id, role=role, jti=jti, exp=exp)
    payload: dict[str, Any] = {
        "user_id": user_id,
        "account_id": account_id,
        "role": role,
        "jti": jti,
        "exp": exp,
    }
    token = jwt.encode(payload, get_private_key(), algorithm=ALGORITHM)
    return token, claims


def issue_refresh_token(user_id: str) -> tuple[str, str]:
    """Returns (token, jti). Refresh tokens are opaque to other services;
    only the Auth Service tracks them (in refresh_tokens table)."""
    jti = str(uuid.uuid4())
    exp = int(time.time()) + REFRESH_TOKEN_TTL_SECONDS
    payload = {"user_id": user_id, "jti": jti, "exp": exp, "type": "refresh"}
    token = jwt.encode(payload, get_private_key(), algorithm=ALGORITHM)
    return token, jti


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, get_public_key(), algorithms=[ALGORITHM])
