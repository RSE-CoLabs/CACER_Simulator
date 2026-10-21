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
from source.data_structures import OwnershipResults


def calculate_ownership(
    *,
    users: Mapping[str, Mapping[str, Any]],
    plants: Mapping[str, Mapping[str, Any]],
    membership_matrix: pd.DataFrame,
    plant_operation_matrix: pd.DataFrame,
    monthly_calendar: pd.DataFrame,
    funding_schemes: pd.DataFrame,
    scenario: Mapping[str, Any],
    repartition_schemes: pd.DataFrame,
    surplus_schemes: pd.DataFrame,
    capex_table: pd.DataFrame,
    scale_factors: pd.DataFrame,
) -> OwnershipResults:
    """Build ownership and allocation matrices from explicit values."""
    months = monthly_calendar["month"].tolist()
    month_numbers = monthly_calendar["month_number"].astype(int).tolist()
    membership = membership_matrix.drop(index="month", errors="ignore").astype(
        float
    )
    subscription = membership.copy()
    non_january = [
        column
        for column, month in zip(subscription.columns, months)
        if not month.endswith("-01")
    ]
    subscription.loc[:, non_january] = 0

    ordered_users = [name for name in membership.index if name in users]
    investment = pd.DataFrame(
        0.0,
        index=[*ordered_users, "CACER", "ESCo"],
        columns=plants,
    )
    ownership: dict[str, pd.DataFrame] = {}
    for plant, values in plants.items():
        funding = funding_schemes.loc[values["funding_scheme"]].fillna(0)
        esco = bool(funding["ESCo_flag"])
        if esco:
            investment.loc["ESCo", plant] = 1.0
        else:
            for stakeholder, share in funding.drop(
                labels=["Ownership", "ESCo_flag"],
                errors="ignore",
            ).items():
                share = float(share)
                if not share:
                    continue
                if stakeholder == "Titolare POD":
                    investment.loc[values["titolare_POD"], plant] += share
                elif stakeholder == "CACER members":
                    active = membership[
                        int(values["disbursement_month"])
                    ]
                    investors = [
                        user
                        for user in users
                        if active[user] and not users[user]["dummy_user"]
                    ]
                    investment.loc[investors, plant] += share / len(investors)
                else:
                    investment.loc[stakeholder, plant] += share
        if not np.isclose(investment[plant].sum(), 1.0):
            raise ValueError(f"Investment shares do not sum to one: {plant}")

        frame = pd.DataFrame(
            0.0,
            index=investment.index[investment[plant] > 0],
            columns=month_numbers,
        )
        operation = plant_operation_matrix.loc[plant].astype(float)
        for owner in frame.index:
            frame.loc[owner] = (
                investment.loc[owner, plant] * operation.to_numpy()
            )
        frame.loc["month"] = months
        ownership[plant] = pd.concat(
            [frame.loc[["month"]], frame.drop(index="month")]
        )

    repartition: dict[str, pd.DataFrame] = {}
    definitions = {
        "incentives": (
            repartition_schemes,
            scenario["Incentives repartition scheme"],
            False,
        ),
        "CACER opex": (
            repartition_schemes,
            scenario["CACER opex repartition scheme"],
            False,
        ),
        "surplus": (
            surplus_schemes,
            scenario["Surplus repartition scheme"],
            True,
        ),
    }
    active_users = [
        user
        for user in membership.index
        if user in users and not users[user]["dummy_user"]
    ]
    for name, (schemes, selected, surplus) in definitions.items():
        scheme = schemes.loc[selected].fillna(0)
        initial_index = (
            [*active_users, "CACER", "social_fund"]
            if surplus
            else ["CACER", *active_users]
        )
        frame = pd.DataFrame(
            0.0,
            index=initial_index,
            columns=membership.columns,
        )
        for item, share in scheme.items():
            share = float(share)
            if not share:
                continue
            if item in {"CACER members - fixed", "Surplus CACER users"}:
                eligible = active_users
                if surplus:
                    eligible = [
                        user
                        for user in eligible
                        if users[user]["type"] != "producer"
                    ]
                weights = membership.loc[eligible]
                weights = weights.div(weights.sum(axis=0), axis=1).fillna(0)
                frame = frame.add(weights * share, fill_value=0)
            elif item == "Prosumers":
                eligible = [
                    user for user in active_users
                    if users[user]["type"] == "prosumer"
                ]
                weights = membership.loc[eligible]
                weights = weights.div(weights.sum(axis=0), axis=1).fillna(0)
                frame = frame.add(weights * share, fill_value=0)
            elif item == "Consumers":
                eligible = [
                    user for user in active_users
                    if users[user]["type"] == "consumer"
                ]
                weights = membership.loc[eligible]
                weights = weights.div(weights.sum(axis=0), axis=1).fillna(0)
                frame = frame.add(weights * share, fill_value=0)
            elif item == "CACER":
                frame.loc["CACER"] = share
            elif item in {"Social Fund", "social_fund"}:
                frame.loc["social_fund"] = share
        frame.loc["month"] = months
        frame.columns = month_numbers
        repartition[name] = pd.concat(
            [frame.loc[["month"]], frame.drop(index="month")]
        )

    plant_capex = {
        plant: calculate_plant_capex(
            values,
            capex_table=capex_table,
            scale_factors=scale_factors,
        )
        for plant, values in plants.items()
    }
    return OwnershipResults(
        subscription,
        ownership,
        investment.replace(0, np.nan),
        repartition,
        plant_capex,
    )


def calculate_plant_capex(
    plant: Mapping[str, Any],
    *,
    capex_table: pd.DataFrame,
    scale_factors: pd.DataFrame,
) -> dict[str, float]:
    """Calculate component CAPEX while preserving legacy scale-factor rules."""
    result: dict[str, float] = {}
    sizes = {
        "pv": float(plant["pv"] or 0),
        "pv_inverter": float(plant["pv"] or 0) * 0.8,
        "battery": float(plant["battery"] or 0),
        "wind": float(plant["wind"] or 0),
        "mv_cabinet": (
            float(plant["pv"] or 0) + float(plant["wind"] or 0)
        ) * bool(plant["mv_cabinet"]),
    }
    for item, size in sizes.items():
        result[f"capex_{item}"] = _item_capex(
            item,
            size,
            capex_table,
            scale_factors,
        )
    for item in ("pv_inverter", "battery"):
        if bool(capex_table.loc["replacement_flag", item]):
            result[f"capex_replacement_{item}"] = _item_capex(
                item,
                sizes[item],
                capex_table,
                scale_factors,
                replacement=True,
            )
    return result


def _item_capex(
    item: str,
    size: float,
    capex_table: pd.DataFrame,
    scale_factors: pd.DataFrame,
    *,
    replacement: bool = False,
) -> float:
    row = "replacement_cost_per_unit" if replacement else "cost_per_unit"
    cost = float(capex_table.loc[row, item])
    bin_index = int(np.digitize(size, scale_factors["Pmax"]))
    factor = float(scale_factors.iloc[bin_index][item])
    quantity = 1.0 if item == "mv_cabinet" else size
    return factor * quantity * cost
