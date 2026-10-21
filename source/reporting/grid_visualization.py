from __future__ import annotations

import pandapower.plotting as plot
import plotly.express as px


def network_figure(network, *, title: str = "Grid network"):
    """Return a Plotly network figure without saving it."""
    figure = plot.simple_plotly(network, aspectratio=(2, 1), figsize=2)
    figure.update_layout(title=title)
    return figure


def bus_voltage_figure(
    bus_voltage,
    *,
    title: str = "Bus voltage",
):
    """Return bus-voltage time series from an explicit result table."""
    figure = px.line(
        bus_voltage,
        x=bus_voltage.index,
        y=list(bus_voltage.columns),
    )
    figure.update_layout(title=title, yaxis_title="Voltage [p.u.]")
    return figure


def line_loading_figure(
    line_loading,
    *,
    title: str = "Line loading",
):
    """Return line-loading time series from an explicit result table."""
    figure = px.line(
        line_loading,
        x=line_loading.index,
        y=list(line_loading.columns),
    )
    figure.update_layout(title=title, yaxis_title="Loading [%]")
    return figure


def transformer_loading_figure(
    transformer_loading,
    *,
    title: str = "Transformer loading",
):
    """Return transformer-loading time series from an explicit result table."""
    figure = px.line(
        transformer_loading,
        x=transformer_loading.index,
        y=list(transformer_loading.columns),
    )
    figure.update_layout(title=title, yaxis_title="Loading [%]")
    return figure
