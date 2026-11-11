"""Calendar-related presentation helpers."""

from datetime import date

import pandas as pd
import streamlit as st


def show_days_off(days_off) -> None:
    if not days_off:
        st.info("Nenhuma folga registrada neste mês.")
        return
    table = pd.DataFrame(
        [
            {
                "Data": day_off.data.strftime("%d/%m/%Y"),
                "Status": day_off.status.capitalize(),
                "Observação": day_off.observacao or "—",
            }
            for day_off in days_off
        ]
    )
    st.dataframe(table, hide_index=True, width="stretch")


def month_bounds(selected: date) -> tuple[date, date]:
    first = selected.replace(day=1)
    if first.month == 12:
        next_month = date(first.year + 1, 1, 1)
    else:
        next_month = date(first.year, first.month + 1, 1)
    return first, date.fromordinal(next_month.toordinal() - 1)
