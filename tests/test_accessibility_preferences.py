from decimal import Decimal

import pytest

from services.auth_service import register_user
from services.preferencias_service import (
    PreferenciasError,
    get_accessibility_preferences,
    save_accessibility_preferences,
)


def test_accessibility_preferences_are_saved_per_account(session):
    first = register_user(session, "Conta Um", "um@example.com", "senha-conta-um-123")
    second = register_user(session, "Conta Dois", "dois@example.com", "senha-conta-dois-123")

    saved = save_accessibility_preferences(
        session, first.id, "escuro", True, Decimal("1.25"), True
    )

    assert saved.tema == "escuro"
    assert saved.alto_contraste
    assert saved.escala_texto == Decimal("1.25")
    assert saved.reduzir_animacoes
    assert get_accessibility_preferences(session, second.id).tema == "sistema"


def test_invalid_accessibility_preferences_are_rejected(session):
    user = register_user(session, "Ana Silva", "ana@example.com", "senha-segura-123")

    with pytest.raises(PreferenciasError, match="tema"):
        save_accessibility_preferences(
            session, user.id, "neon", False, Decimal("1.00"), False
        )
    with pytest.raises(PreferenciasError, match="texto"):
        save_accessibility_preferences(
            session, user.id, "claro", False, Decimal("1.05"), False
        )
