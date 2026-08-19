"""Fernet-based token-at-rest encryption for LinkedIn access/refresh
tokens, and a separate Fernet key for signing short-lived OAuth `state`
values. Two distinct keys even though both are placeholders in dev, so
rotating one (e.g. after a state-signing key leak) never touches the
other (stored user tokens)."""
import json

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_token_fernet = Fernet(settings.token_encryption_key.encode())
_state_fernet = Fernet(settings.oauth_state_key.encode())


def encrypt_token(value: str) -> str:
    return _token_fernet.encrypt(value.encode()).decode()


def decrypt_token(value: str) -> str:
    return _token_fernet.decrypt(value.encode()).decode()


def create_oauth_state(account_id: str, user_id: str) -> str:
    # Fernet tokens embed their own creation timestamp, checked against
    # `ttl` on decrypt below — no need to encode an expiry ourselves.
    payload = json.dumps({"account_id": account_id, "user_id": user_id})
    return _state_fernet.encrypt(payload.encode()).decode()


def verify_oauth_state(state: str) -> dict[str, str]:
    try:
        payload = json.loads(_state_fernet.decrypt(state.encode(), ttl=settings.oauth_state_ttl_seconds))
    except InvalidToken as exc:
        raise ValueError("Invalid or expired OAuth state.") from exc
    return payload
