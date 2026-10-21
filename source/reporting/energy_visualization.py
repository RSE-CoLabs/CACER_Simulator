from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def plot_scatter(
    x: Sequence[float],
    y: Sequence[float],
    title: str,
    title_y: str,
) -> go.Figure:
    figure = go.Figure(go.Scatter(x=x, y=y, mode="lines"))
    figure.update_layout(title=title, xaxis_title="Datetime", yaxis_title=title_y)
    return figure


def plot_sankey(
    totals: Mapping[str, float] | pd.Series,
    user: str,
) -> go.Figure:
    """Return the accepted consumption/production Sankey topology."""
    values = pd.Series(totals, dtype=float).fillna(0)
    required = {"Eprod", "Eaut", "Eimm", "Eut", "Eprel"}
    missing = sorted(required.difference(values.index))
    if missing:
        raise ValueError(f"Energy totals miss Sankey fields: {missing}")
    labels = [
        "Production",
        "Self-consumption",
        "Grid injection",
        "Consumption",
        "Grid withdrawal",
    ]
    source = [0, 0, 1, 4]
    target = [1, 2, 3, 3]
    sankey_values = [
        values["Eaut"],
        values["Eimm"],
        values["Eaut"],
        values["Eprel"],
    ]
    return go.Figure(
        go.Sankey(
            node={"label": labels},
            link={"source": source, "target": target, "value": sankey_values},
        ),
        layout={"title": f"Energy flows - {user}"},
    )


def plot_pie_consumption(
    totals: Mapping[str, float] | pd.Series,
    user: str,
) -> go.Figure:
    values = pd.Series(totals, dtype=float).fillna(0)
    return px.pie(
        names=["Self-consumption", "Grid withdrawal"],
        values=[values.get("Eaut", 0), values.get("Eprel", 0)],
        title=f"{user} Energy consumption allocation - [%]",
    )


def plot_pie_generation(
    totals: Mapping[str, float] | pd.Series,
    user: str,
) -> go.Figure:
    values = pd.Series(totals, dtype=float).fillna(0)
    return px.pie(
        names=["Self-consumption", "Grid injection"],
        values=[values.get("Eaut", 0), values.get("Eimm", 0)],
        title=f"{user} Energy generation allocation - [%]",
    )


def plot_area_lifetime_consumption(
    frame: pd.DataFrame,
    user: str,
) -> go.Figure:
    return _area(
        frame,
        ("Eaut", "Eprel"),
        f"Energy consumption repartition - {user}",
    )


def plot_area_year1_consumption(
    frame: pd.DataFrame,
    user: str,
) -> go.Figure:
    return _area(
        _first_year(frame),
        ("Eaut", "Eprel"),
        f"Energy consumption repartition for the first year - {user}",
    )


def plot_area_lifetime_generation(
    frame: pd.DataFrame,
    user: str,
) -> go.Figure:
    return _area(
        frame,
        ("Eaut", "Eimm"),
        f"Energy generation repartition - {user}",
    )


def plot_area_year1_generation(
    frame: pd.DataFrame,
    user: str,
) -> go.Figure:
    return _area(
        _first_year(frame),
        ("Eaut", "Eimm"),
        f"Energy generation repartition for the first year - {user}",
    )


def daily_energy_flows_figure(
    frame: pd.DataFrame,
    day: str | pd.Timestamp,
    *,
    user: str,
) -> go.Figure:
    timestamp = pd.Timestamp(day)
    index = pd.to_datetime(frame.index)
    daily = frame.loc[index.normalize() == timestamp.normalize()]
    columns = [
        column
        for column in ("Eut", "Eprod", "Eaut", "Eprel", "Eimm")
        if column in daily
    ]
    figure = px.line(daily, x=daily.index, y=columns)
    figure.update_layout(
        title=f"Energy flows - {timestamp.date()} - {user}",
        yaxis_title="Energy [kWh]",
    )
    return figure


def energy_summary_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Return energy totals used by Sankey and allocation charts."""
    numeric = frame.select_dtypes("number")
    return numeric.sum().to_frame("total_kwh")


def _area(
    frame: pd.DataFrame,
    columns: Sequence[str],
    title: str,
) -> go.Figure:
    available = [column for column in columns if column in frame]
    figure = px.area(frame, x=frame.index, y=available)
    figure.update_layout(title=title, yaxis_title="Energy [kWh]")
    return figure


def _first_year(frame: pd.DataFrame) -> pd.DataFrame:
    index = pd.to_datetime(frame.index)
    if index.empty:
        return frame
    return frame.loc[index.year == index[0].year]
