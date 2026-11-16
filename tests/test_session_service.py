import pytest

from services.session_service import (
    SESSION_TTL_SECONDS,
    create_remember_token,
    get_remembered_user_id,
)


def test_remember_token_identifies_user_until_expiration():
    token = create_remember_token(42, b"secret-key", now=1000)

    assert get_remembered_user_id(token, b"secret-key", now=1000) == 42
    assert (
        get_remembered_user_id(
            token, b"secret-key", now=1000 + SESSION_TTL_SECONDS
        )
        is None
    )


def test_remember_token_rejects_tampering_and_other_secrets():
    token = create_remember_token(42, b"secret-key", now=1000)
    payload, signature = token.split(".", maxsplit=1)
    changed_first_character = "A" if payload[0] != "A" else "B"
    tampered_token = f"{changed_first_character}{payload[1:]}.{signature}"

    assert get_remembered_user_id(token, b"other-secret", now=1000) is None
    assert get_remembered_user_id(tampered_token, b"secret-key", now=1000) is None


def test_remember_token_requires_a_positive_integer_user_id():
    with pytest.raises(ValueError):
        create_remember_token(0, b"secret-key", now=1000)
