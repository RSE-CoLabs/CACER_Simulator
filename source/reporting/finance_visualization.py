from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def financial_sums(
    user_cash_flows: Mapping[str, Mapping[str, pd.DataFrame]],
) -> pd.DataFrame:
    """Aggregate explicit user cash-flow tables using the legacy grouping."""
    user_results: list[pd.DataFrame] = []
    for user, sheets in user_cash_flows.items():
        sheet_results: list[pd.DataFrame] = []
        for sheet, cash_flows in sheets.items():
            frame = cash_flows.drop(index="month", errors="ignore")
            aggregated = frame.sum(axis=1)
            selected_index = [
                index
                for index in aggregated.index
                if str(index).startswith(("capex", "opex", "revenues"))
            ]
            selected = (
                aggregated.loc[selected_index]
                .reset_index(name="value")
                .rename(columns={"index": "item"})
            )
            selected = selected.loc[selected["value"] != 0].copy()
            selected["source"] = sheet
            selected["target"] = user
            sheet_results.append(selected)
        if sheet_results:
            user_result = pd.concat(sheet_results, ignore_index=True)
            if user_result.isnull().values.any():
                raise ValueError(
                    f"There are NaN values in the {user} merged dataframe"
                )
            user_results.append(user_result)
    if not user_results:
        return pd.DataFrame(
            columns=["item", "value", "source", "target", "sign"]
        )
    results = pd.concat(user_results, ignore_index=True)
    results["sign"] = "cost"
    results.loc[results["value"] > 0, "sign"] = "revenue"
    results["value"] = results["value"].abs()
    return results


def bill_line_figure(
    monthly_bill: pd.DataFrame,
    *,
    user: str,
    scenario: str,
) -> go.Figure:
    figure = px.line(monthly_bill, x=monthly_bill.index, y=list(monthly_bill))
    figure.update_layout(
        title=f"Bills user {user} in scenario {scenario} - line chart"
    )
    return figure


def bill_pie_figure(
    bill_totals: pd.Series,
    *,
    user: str,
    scenario: str,
) -> go.Figure:
    return px.pie(
        names=bill_totals.index,
        values=bill_totals.values,
        title=f"Bills user {user} in scenario {scenario} - pie chart",
    )


def financial_series_figure(
    frame: pd.DataFrame,
    *,
    columns: Sequence[str] | None = None,
    title: str,
    y_title: str = "EUR",
) -> go.Figure:
    selected = frame.loc[:, list(columns)] if columns is not None else frame
    figure = px.line(selected, x=selected.index, y=list(selected.columns))
    figure.update_layout(title=title, yaxis_title=y_title)
    return figure


def cash_flow_figure(
    cash_flows: pd.DataFrame,
    *,
    title: str,
) -> go.Figure:
    figure = px.bar(
        cash_flows,
        x=cash_flows.index,
        y=list(cash_flows.columns),
        barmode="relative",
    )
    figure.update_layout(title=title, yaxis_title="Cash flow [EUR]")
    return figure


def dcf_table(
    results: pd.DataFrame,
    *,
    fields: Sequence[str] = ("IRR", "NPV", "Payback Period"),
) -> pd.DataFrame:
    missing = sorted(set(fields).difference(results.index))
    if missing:
        raise ValueError(f"Financial results miss fields: {missing}")
    return results.loc[list(fields)]


def financial_table_figure(
    table: pd.DataFrame,
    *,
    title: str,
) -> go.Figure:
    display = table.reset_index()
    return go.Figure(
        go.Table(
            header={"values": list(display.columns)},
            cells={"values": [display[column] for column in display]},
        ),
        layout={"title": title},
    )
