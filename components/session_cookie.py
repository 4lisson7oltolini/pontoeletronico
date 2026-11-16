"""Browser cookie synchronization for short-lived remembered sessions."""

import logging
import os
import secrets
from functools import lru_cache

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from services.session_service import SESSION_TTL_SECONDS

logger = logging.getLogger(__name__)
COOKIE_NAME = "ponto_facil_session"
_PROCESS_SESSION_SECRET = secrets.token_bytes(32)

_COOKIE_SYNC = st.components.v2.component(
    "ponto_facil.session_cookie_sync",
    html="<span hidden></span>",
    js="""
export default function(component) {
    const { data } = component;
    if (!data) return;

    let cookie = `${data.name}=${data.value}; Path=/; Max-Age=${data.maxAge}; SameSite=Lax`;
    if (window.location.protocol === "https:") cookie += "; Secure";
    document.cookie = cookie;
}
""",
)

_CONSENT_SYNC = st.components.v2.component(
    "ponto_facil.consent_sync",
    html="<span hidden></span>",
    js="""
export default function(component) {
    const { data, setStateValue } = component;
    if (!data) return;

    let accepted = false;
    let available = true;
    try {
        const storedValue = window.localStorage.getItem(data.storageKey);
        let stored = null;
        if (storedValue) {
            try {
                stored = JSON.parse(storedValue);
            } catch (error) {
                stored = null;
            }
        }

        if (data.choice === "Sim") {
            if (
                !stored ||
                stored.version !== data.version ||
                typeof stored.acceptedAt !== "string"
            ) {
                window.localStorage.setItem(
                    data.storageKey,
                    JSON.stringify({
                        version: data.version,
                        acceptedAt: new Date().toISOString()
                    })
                );
            }
            accepted = true;
        } else if (data.choice === "Não") {
            window.localStorage.removeItem(data.storageKey);
        } else if (stored) {
            accepted = Boolean(
                stored.version === data.version &&
                typeof stored.acceptedAt === "string"
            );
        }
    } catch (error) {
        available = false;
        accepted = false;
    }

    setStateValue("accepted", accepted);
    setStateValue("available", available);
}
""",
)


@lru_cache(maxsize=1)
def get_session_secret() -> bytes:
    configured_secret = os.getenv("SESSION_SECRET")
    if not configured_secret:
        try:
            configured_secret = st.secrets.get("SESSION_SECRET")
        except (FileNotFoundError, StreamlitSecretNotFoundError):
            configured_secret = None

    if configured_secret:
        return str(configured_secret).encode("utf-8")

    logger.warning(
        "SESSION_SECRET não configurada; sessões lembradas serão invalidadas "
        "quando o processo da aplicação reiniciar."
    )
    return _PROCESS_SESSION_SECRET


def set_session_cookie(token: str | None) -> None:
    _COOKIE_SYNC(
        data={
            "name": COOKIE_NAME,
            "value": token or "",
            "maxAge": SESSION_TTL_SECONDS if token else 0,
        },
        key="ponto_facil_session_cookie",
    )


def sync_browser_consent(
    version: str, choice: str | None = None
) -> tuple[bool, bool]:
    result = _CONSENT_SYNC(
        data={
            "storageKey": "ponto_facil_consent",
            "version": version,
            "choice": choice,
        },
        key=f"ponto_facil_consent_{version}",
        default={"accepted": False, "available": False},
        on_accepted_change=lambda: None,
        on_available_change=lambda: None,
    )
    return result.accepted is True, result.available is True
