"""Reusable dashboard metric cards."""

import streamlit as st


def metric_card(label: str, value: str, help_text: str | None = None) -> None:
    st.metric(label=label, value=value, help=help_text, border=True)
