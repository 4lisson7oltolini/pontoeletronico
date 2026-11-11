from decimal import Decimal

from services.preferencias_service import PreferenciasAcessibilidade
from utils.accessibility import apply_accessibility_preferences


def test_primary_button_styles_match_streamlit_form_submit_testid(monkeypatch):
    styles = []
    monkeypatch.setattr(
        "utils.accessibility.st.markdown",
        lambda body, **kwargs: styles.append(body),
    )
    preferences = PreferenciasAcessibilidade(tema="escuro")

    apply_accessibility_preferences(preferences)

    css = styles[0]
    streamlit_submit_testid = "stBaseButton-primaryFormSubmit"
    assert streamlit_submit_testid.startswith("stBaseButton-primary")
    assert '[data-testid^="stBaseButton-primary"]' in css
    assert "background-color: var(--pf-primary) !important" in css
    assert "color: var(--pf-primary-text) !important" in css
    assert "--pf-primary: #93c5fd" in css
    assert "--pf-primary-text: #0b1220" in css


def test_high_contrast_and_text_scale_are_included_in_styles(monkeypatch):
    styles = []
    monkeypatch.setattr(
        "utils.accessibility.st.markdown",
        lambda body, **kwargs: styles.append(body),
    )
    preferences = PreferenciasAcessibilidade(
        tema="escuro",
        alto_contraste=True,
        escala_texto=Decimal("1.25"),
        reduzir_animacoes=True,
    )

    apply_accessibility_preferences(preferences)

    css = styles[0]
    assert "--pf-primary: #ffeb00" in css
    assert "font-size: 125%" in css
    assert "animation-duration: 0.01ms" in css
