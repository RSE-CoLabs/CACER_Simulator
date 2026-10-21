from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def load_profile_figure(
    profiles: pd.DataFrame,
    *,
    columns: Sequence[str] | None = None,
    title: str = "Load profiles",
    y_title: str = "Energy [kWh]",
) -> go.Figure:
    """Return a line chart for selected load profiles."""
    selected = profiles.loc[:, list(columns)] if columns is not None else profiles
    figure = px.line(selected, x=selected.index, y=list(selected.columns))
    figure.update_layout(title=title, xaxis_title="Datetime", yaxis_title=y_title)
    return figure


def daily_load_profile_figure(
    profiles: pd.DataFrame,
    day: str | pd.Timestamp,
    *,
    title: str | None = None,
) -> go.Figure:
    """Return load profiles for one explicit calendar day."""
    timestamp = pd.Timestamp(day)
    index = pd.to_datetime(profiles.index)
    daily = profiles.loc[index.normalize() == timestamp.normalize()]
    return load_profile_figure(
        daily,
        title=title or f"Load profiles - {timestamp.date()}",
    )


def aggregate_load_table(profiles: pd.DataFrame) -> pd.DataFrame:
    """Return totals and peaks used by reporting tables."""
    return pd.DataFrame(
        {
            "total_kwh": profiles.sum(),
            "peak_kwh": profiles.max(),
            "mean_kwh": profiles.mean(),
        }
    )
