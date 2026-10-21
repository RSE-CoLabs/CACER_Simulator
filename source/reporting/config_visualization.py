from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd
import plotly.graph_objects as go


def color_tipologia(
    value: str,
    colors: Mapping[str, str],
) -> str:
    """Return the legacy user-type CSS color from an explicit palette."""
    color_name = {
        "prosumer": "arancione",
        "producer": "blu",
    }.get(value, "verde")
    return f"color: {colors[color_name]}"


def color_categoria(
    value: str,
    colors: Mapping[str, str],
) -> str:
    """Return the legacy user-category CSS color from an explicit palette."""
    color_name = {
        "domestico": "rosso",
        "industriale": "violetto",
        "pubblico": "azzurro",
    }.get(value, "marrone")
    return f"color: {colors[color_name]}"


def configuration_summary_table(
    recap: Mapping[str, Any],
) -> pd.DataFrame:
    """Return a two-column configuration summary table."""
    rows = []
    for key, value in recap.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            rows.append((key, value))
    return pd.DataFrame(rows, columns=["parameter", "value"])


def registry_summary_table(
    registry: Mapping[str, Mapping[str, Any]],
    *,
    fields: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Return a normalized user, plant, or configuration registry table."""
    frame = pd.DataFrame.from_dict(registry, orient="index")
    frame.index.name = "id"
    if fields is not None:
        missing = sorted(set(fields).difference(frame.columns))
        if missing:
            raise ValueError(f"Registry misses requested fields: {missing}")
        frame = frame.loc[:, list(fields)]
    return frame


def summary_table_figure(
    table: pd.DataFrame,
    *,
    title: str,
) -> go.Figure:
    """Render a configuration table without reading or saving data."""
    display = table.reset_index()
    return go.Figure(
        data=[
            go.Table(
                header={
                    "values": list(display.columns),
                    "fill_color": "#1f4e78",
                    "font": {"color": "white"},
                },
                cells={
                    "values": [display[column] for column in display],
                    "fill_color": "#f4f6f7",
                },
            )
        ],
        layout={"title": title},
    )
