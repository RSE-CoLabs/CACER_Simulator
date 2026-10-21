from __future__ import annotations

import calendar
import contextlib
import csv
from datetime import datetime
import datetime as dt
import glob
import io
import math
import os
from pathlib import Path
from random import random
from typing import Any, Mapping

import numpy as np
import numpy_financial as npf
import pandas as pd
from simple_colors import blue, green, red
from tqdm.auto import tqdm
import yaml

from source.config.utilities import province_to_region
from source.data_structures import BillingResults


def calculate_bills(
    *,
    energy_user_flows: Mapping[str, pd.DataFrame],
    user_types: Mapping[str, Mapping[str, Any]],
    recap: Mapping[str, Any],
    calendar_frame: pd.DataFrame,
    market_assumptions: Mapping[str, Any],
    pun_monthly: pd.DataFrame,
    market_scenario: str,
    delta_t: str,
) -> BillingResults:
    """Calculate user-type and CACER bills from explicit in-memory values."""
    bills: dict[str, dict[str, pd.DataFrame]] = {}
    for user_type, values in user_types.items():
        if not bool(values["consuming"]):
            continue
        bills[user_type] = calculate_user_type_bill(
            energy_user_flows[user_type],
            values,
            calendar_frame=calendar_frame,
            market_assumptions=market_assumptions,
            pun_monthly=pun_monthly,
            market_scenario=market_scenario,
            delta_t=delta_t,
        )

    aggregated: dict[str, dict[str, pd.DataFrame]] = {}
    groups = ["project", *recap["stakeholders"], *recap["configurations"]]
    for group in groups:
        if group == "project":
            selected = (
                recap["list_types_consumers_CACER"]
                + recap["list_types_prosumers_CACER"]
            )
        elif group in recap["stakeholders"]:
            selected = [
                name
                for name, values in user_types.items()
                if values["stakeholder"] == group
                and values["consuming"]
                and not values["dummy_user"]
            ]
        else:
            selected = [
                name
                for name, values in user_types.items()
                if values["CP"] == group
                and values["consuming"]
                and not values["dummy_user"]
            ]
        aggregated[group] = {}
        for scenario in ("bau", "pv"):
            total = None
            for name in selected:
                available = scenario if scenario in bills[name] else "bau"
                values = (
                    bills[name][available]["total_bill_cost"]
                    * int(user_types[name]["num"])
                )
                total = values.copy() if total is None else total.add(values)
            aggregated[group][scenario] = total.to_frame("total_bill_cost")
    return BillingResults(bills, aggregated)


def calculate_user_type_bill(
    flow: pd.DataFrame,
    user_type: Mapping[str, Any],
    *,
    calendar_frame: pd.DataFrame,
    market_assumptions: Mapping[str, Any],
    pun_monthly: pd.DataFrame,
    market_scenario: str,
    delta_t: str,
) -> dict[str, pd.DataFrame]:
    """Calculate all bill scenarios for one consuming user type."""
    frame = flow[["Eprel", "Eaut"]].fillna(0).copy()
    frame.index = pd.DatetimeIndex(frame.index)
    for column in ("Eprel", "Eaut"):
        if (frame[column] == frame[column].astype(int)).all():
            frame[column] = frame[column].astype(int)
    frame["month"] = frame.index.strftime("%Y-%m")
    frame["year"] = frame.index.year.astype("int64")
    frame["month_number"] = frame.index.month.astype("int64")
    frame["year_index"] = (
        frame["year"] - frame["year"].min()
    ).astype("int64")
    category = str(user_type["category"])
    supplier = str(user_type["supplier"])
    scheme = str(user_type["tariff"])
    voltage = str(user_type["voltage"])
    power_range = str(user_type["power_range"])
    assumptions = market_assumptions[category]
    variation_energy = market_assumptions["variazione_annua"][
        market_scenario
    ]
    variation_transport = market_assumptions["variazione_annua"][
        "trasporto"
    ]
    variation_ogs = market_assumptions["variazione_annua"]["ogs"]
    indexed = supplier in {"indexed", "indexed_ciappartiene_CER"}
    if indexed:
        frame["energy_price"] = (
            frame["month_number"].map(pun_monthly["eur/MWh"]) / 1000
        )
    else:
        tariffs = assumptions[supplier][scheme]
        if scheme == "schema_1":
            frame["energy_price"] = float(tariffs["F1"])
        else:
            bands = calendar_frame.set_index("datetime")["fascia"].replace(
                {1: "F1", 2: "F2", 3: "F3"}
            )
            tariffs = dict(tariffs)
            tariffs["F2"] = tariffs["F1"]
            tariffs["F3"] = tariffs["F2"]
            frame["fascia"] = bands.reindex(frame.index)
            frame["energy_price"] = frame["fascia"].map(tariffs)
    frame["yearly_variation_me"] = frame["year_index"].map(
        dict(enumerate(variation_energy))
    )
    frame["yearly_variation_transport"] = frame["year_index"].map(
        dict(enumerate(variation_transport))
    )
    frame["yearly_variation_ogs"] = frame["year_index"].map(
        dict(enumerate(variation_ogs))
    )
    for column in (
        "yearly_variation_me",
        "yearly_variation_transport",
        "yearly_variation_ogs",
    ):
        if (frame[column] == frame[column].astype(int)).all():
            frame[column] = frame[column].astype(int)

    losses = float(
        market_assumptions[
            "perdite_prelievo_BT" if voltage == "BT" else "perdite_prelievo_MT"
        ]
    )
    intervals = 365 * 24 * (4 if delta_t.lower() == "15min" else 1)
    contractual_power = _contractual_power(power_range, frame["Eprel"], delta_t)
    energy_items = [name for name in assumptions if name.endswith("_energy")]
    fixed_items = [name for name in assumptions if name.endswith("_fixed")]
    power_items = [name for name in assumptions if name.endswith("_power")]
    base_columns = frame.columns
    scenarios = ["pv", "bau"] if user_type["type"] == "prosumer" else ["bau"]
    results: dict[str, pd.DataFrame] = {}
    for scenario in scenarios:
        current = frame[base_columns].copy()
        current["load_active"] = current["Eprel"] + (
            scenario == "bau"
        ) * current["Eaut"]
        current["load_active_corrected"] = current["load_active"] * (1 + losses)
        current["energy_price_corrected"] = (
            current["yearly_variation_me"] * current["energy_price"]
        )
        if indexed:
            indexed_inputs = assumptions[supplier]
            if supplier == "indexed":
                current["energy_price_corrected"] += float(
                    indexed_inputs["spread"]
                )
            else:
                current["hour"] = current.index.hour
                current["spread"] = float(indexed_inputs["spread_night"])
                day = (current["hour"] < 18) & (current["hour"] >= 9)
                current.loc[day, "spread"] = float(
                    indexed_inputs["spread_day"]
                )
                current["energy_price_corrected"] += current["spread"]
        current["me_energy"] = (
            current["load_active_corrected"]
            * current["energy_price_corrected"]
        )
        for item in energy_items + fixed_items + power_items:
            tariff = assumptions[item]
            if indexed and item == "me_PCV_fixed":
                tariff = assumptions["indexed"][item]
            if item in energy_items:
                variation = (
                    "yearly_variation_me"
                    if item.startswith("me")
                    else "yearly_variation_transport"
                    if item.startswith("transport")
                    else "yearly_variation_ogs"
                )
                current[item] = (
                    current["load_active_corrected"]
                    * float(tariff)
                    * current[variation]
                )
            elif item in fixed_items:
                current[item] = float(tariff) / intervals
            else:
                current[item] = contractual_power * float(tariff) / intervals
        for family in ("me", "transport", "ogs"):
            current[f"{family}_cost"] = current[
                [name for name in current if name.startswith(family)]
            ].sum(axis=1)
        for family in ("energy", "fixed", "power"):
            current[f"{family}_cost"] = current[
                [name for name in current if name.endswith(family)]
            ].sum(axis=1)
        current["subtotal_before_taxes"] = current[
            ["me_cost", "transport_cost", "ogs_cost"]
        ].sum(axis=1)
        duty = float(assumptions["duty"])
        if power_range in {"0<P<=1.5", "1.5<P<=3"} and category == "domestico":
            cumulative = current.groupby("month")["load_active"].cumsum()
            current["load_active_cumsum_monthly"] = cumulative
            current["load_active_duty"] = np.maximum(0, cumulative - 150)
            current["duty_cost"] = (
                duty
                * (current["load_active_duty"] > 0)
                * current["load_active"]
            )
        else:
            current["duty_cost"] = duty * current["load_active"]
        current["vat_cost"] = float(assumptions["vat"]) * (
            current["subtotal_before_taxes"] + current["duty_cost"]
        )
        current["total_bill_cost"] = (
            current["subtotal_before_taxes"]
            + current["duty_cost"]
            + current["vat_cost"]
        )
        columns = [
            name for name in current if name.endswith("_cost")
        ] + ["load_active", "load_active_corrected"]
        results[scenario] = current.groupby("month")[columns].sum()
        quarterly = current[current["year_index"] == 0].copy()
        quarterly.index = quarterly.index.strftime("%Y-%m-%d %H:%M:%S")
        quarterly.index.name = "datetime"
        results[f"{scenario}_quarterly"] = quarterly
    return results


def _contractual_power(
    power_range: str,
    load: pd.Series,
    delta_t: str,
) -> float:
    known = {
        "0<P<=1.5": 1.5,
        "1.5<P<=3": 3.0,
        "3<P<=4.5": 4.5,
        "4.5<P<=6": 6.0,
    }
    if power_range in known:
        return known[power_range]
    factor = 4 if delta_t.lower() == "15min" else 1
    return float(load.max()) * factor * 1.3
