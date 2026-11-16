"""Short-lived tokens used to restore an authenticated browser session."""

import base64
import binascii
import hashlib
import hmac
import secrets
import time

SESSION_TTL_SECONDS = 10 * 60


def create_remember_token(
    user_id: int, secret: bytes, now: int | None = None
) -> str:
    if type(user_id) is not int or user_id < 1:
        raise ValueError("O ID do usuário deve ser um inteiro positivo.")
    if not secret:
        raise ValueError("A chave de sessão não pode ser vazia.")

    expires_at = int(time.time() if now is None else now) + SESSION_TTL_SECONDS
    payload = f"{user_id}:{expires_at}:{secrets.token_urlsafe(16)}".encode("ascii")
    encoded_payload = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    signature = hmac.new(secret, encoded_payload.encode("ascii"), hashlib.sha256)
    encoded_signature = base64.urlsafe_b64encode(signature.digest()).decode("ascii").rstrip("=")
    return f"{encoded_payload}.{encoded_signature}"


def get_remembered_user_id(
    token: str, secret: bytes, now: int | None = None
) -> int | None:
    if not isinstance(token, str) or len(token) > 512 or not secret:
        return None

    try:
        encoded_payload, encoded_signature = token.split(".", maxsplit=1)
        expected_signature = hmac.new(
            secret, encoded_payload.encode("ascii"), hashlib.sha256
        ).digest()
        supplied_signature = base64.urlsafe_b64decode(
            encoded_signature + "=" * (-len(encoded_signature) % 4)
        )
        if not hmac.compare_digest(expected_signature, supplied_signature):
            return None

        payload = base64.urlsafe_b64decode(
            encoded_payload + "=" * (-len(encoded_payload) % 4)
        ).decode("ascii")
        user_id_text, expires_at_text, _nonce = payload.split(":", maxsplit=2)
        user_id = int(user_id_text)
        expires_at = int(expires_at_text)
    except (ValueError, UnicodeError, binascii.Error):
        return None

    current_time = int(time.time() if now is None else now)
    if user_id < 1 or expires_at <= current_time:
        return None
    return user_id
