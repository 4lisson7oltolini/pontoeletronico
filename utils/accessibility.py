"""Per-account accessible color, typography, and motion styles for Streamlit."""

from decimal import Decimal

import streamlit as st

from services.preferencias_service import PreferenciasAcessibilidade


def apply_accessibility_preferences(preferences: PreferenciasAcessibilidade) -> None:
    scale = float(preferences.escala_texto)
    if preferences.alto_contraste:
        light = (
            "--pf-bg: #ffffff; --pf-panel: #ffffff; --pf-text: #000000; "
            "--pf-muted: #1a1a1a; --pf-border: #000000; --pf-primary: #0037b8; "
            "--pf-primary-text: #ffffff;"
        )
        dark = (
            "--pf-bg: #000000; --pf-panel: #000000; --pf-text: #ffffff; "
            "--pf-muted: #ffffff; --pf-border: #ffffff; --pf-primary: #ffeb00; "
            "--pf-primary-text: #000000;"
        )
    else:
        light = (
            "--pf-bg: #f8fafc; --pf-panel: #ffffff; --pf-text: #0f172a; "
            "--pf-muted: #475569; --pf-border: #cbd5e1; --pf-primary: #1e3a8a; "
            "--pf-primary-text: #ffffff;"
        )
        dark = (
            "--pf-bg: #0b1220; --pf-panel: #111c2e; --pf-text: #f1f5f9; "
            "--pf-muted: #cbd5e1; --pf-border: #475569; --pf-primary: #334155; "
            "--pf-primary-text: #f8fafc;"
        )

    if preferences.tema == "escuro":
        theme = f":root {{ {dark} color-scheme: dark; }}"
    elif preferences.tema == "claro":
        theme = f":root {{ {light} color-scheme: light; }}"
    else:
        theme = (
            f":root {{ {light} color-scheme: light; }}"
            f"@media (prefers-color-scheme: dark) {{ :root {{ {dark} color-scheme: dark; }} }}"
        )

    motion = (
        "* { animation-duration: 0.01ms !important; animation-iteration-count: 1 !important; "
        "scroll-behavior: auto !important; transition-duration: 0.01ms !important; }"
        if preferences.reduzir_animacoes
        else ""
    )
    st.markdown(
        f"""
        <style>
        {theme}
        html, body, [data-testid="stAppViewContainer"] {{
            background: var(--pf-bg);
            color: var(--pf-text);
            font-size: {scale * 100:g}%;
        }}
        [data-testid="stHeader"], [data-testid="stSidebar"] {{
            background: var(--pf-panel);
            color: var(--pf-text);
        }}
        [data-testid="stMarkdownContainer"], [data-testid="stWidgetLabel"],
        [data-testid="stCaptionContainer"], [data-testid="stMetricLabel"],
        [data-testid="stMetricValue"] {{
            color: var(--pf-text);
        }}
        [data-testid="stCaptionContainer"] {{ color: var(--pf-muted); }}
        [data-testid="stAlert"] {{
            background-color: var(--pf-panel) !important;
            border: 1px solid var(--pf-border);
            color: var(--pf-text) !important;
        }}
        [data-testid="stAlert"] > div {{
            background-color: transparent !important;
            color: var(--pf-text) !important;
        }}
        [data-testid="stAlert"] [data-testid="stMarkdownContainer"],
        [data-testid="stAlert"] p {{
            color: var(--pf-text) !important;
        }}
        [data-testid="stMetric"], [data-testid="stExpander"],
        [data-testid="stDataFrame"], [data-testid="stForm"] {{
            border-color: var(--pf-border);
        }}
        [data-testid="stTextInput"] [data-testid="stTextInputField"],
        [data-testid="stTextArea"] [data-testid="stTextAreaRootElement"],
        [data-testid="stTextArea"] textarea,
        [data-testid="stDateInput"] [data-testid="stDateInputField"],
        [data-testid="stDateInput"] [data-react-aria-pressable="true"],
        [data-testid="stTimeInput"] [data-testid="stTimeInputField"],
        [data-testid="stTimeInput"] [data-react-aria-pressable="true"],
        [data-testid="stNumberInput"] input,
        [data-testid="stSelectbox"] [role="combobox"],
        [data-testid="stMultiSelect"] [role="combobox"] {{
            background-color: var(--pf-panel) !important;
            color: var(--pf-text) !important;
            border-color: var(--pf-border) !important;
        }}
        [data-testid="stDateInput"] [role="spinbutton"],
        [data-testid="stTimeInput"] [role="spinbutton"] {{
            color: var(--pf-text) !important;
        }}
        [data-testid="stDateInputCalendarButton"] {{
            background-color: var(--pf-panel) !important;
            border: 1px solid var(--pf-border) !important;
            color: var(--pf-text) !important;
        }}
        [data-testid="stDateInputCalendarButton"]:hover,
        [data-testid="stDateInputCalendarButton"]:focus-visible {{
            background-color: var(--pf-bg) !important;
            color: var(--pf-text) !important;
        }}
        [data-testid="stTextInput"] [data-testid="stTextInputField"]::placeholder,
        [data-testid="stTextArea"] textarea::placeholder,
        [data-testid="stNumberInput"] input::placeholder {{
            color: var(--pf-muted) !important;
        }}
        [data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button {{
            min-height: 2.75rem;
            border-color: var(--pf-border);
        }}
        [data-testid^="stBaseButton-primary"] {{
            background-color: var(--pf-primary) !important;
            border-color: var(--pf-primary) !important;
            color: var(--pf-primary-text) !important;
        }}
        [data-testid^="stBaseButton-secondary"],
        [data-testid^="stBaseButton-tertiary"] {{
            background-color: var(--pf-panel) !important;
            border-color: var(--pf-border) !important;
            color: var(--pf-text) !important;
        }}
        [data-testid^="stBaseButton-primary"]:hover {{
            filter: brightness(1.12);
        }}
        {motion}
        </style>
        """,
        unsafe_allow_html=True,
    )


def text_scale_from_label(label: str) -> Decimal:
    scales = {
        "90% (compacto)": Decimal("0.90"),
        "100% (padrão)": Decimal("1.00"),
        "110%": Decimal("1.10"),
        "125%": Decimal("1.25"),
        "150% (ampliado)": Decimal("1.50"),
    }
    return scales[label]


def text_scale_label(scale: Decimal) -> str:
    labels = {
        Decimal("0.90"): "90% (compacto)",
        Decimal("1.00"): "100% (padrão)",
        Decimal("1.10"): "110%",
        Decimal("1.25"): "125%",
        Decimal("1.50"): "150% (ampliado)",
    }
    return labels[scale]
