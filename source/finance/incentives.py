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
from source.data_structures import IncentiveResults


def calculate_incentives(
    *,
    pzo_hourly: pd.DataFrame,
    shared_energy_hourly: pd.DataFrame,
    valorization_hourly: pd.DataFrame,
    shared_energy_yearly: pd.DataFrame,
    plants: Mapping[str, Mapping[str, Any]],
    users: Mapping[str, Mapping[str, Any]],
    recap: Mapping[str, Any],
    province: str,
    municipalities: pd.DataFrame,
    monthly_calendar: pd.DataFrame,
    incentive_repartition: pd.DataFrame,
    surplus_repartition: pd.DataFrame,
    cacer_fee_assumptions: Mapping[str, Any],
    trase: float,
    btau: float,
    cpr_bt: float,
    cpr_mt: float,
) -> IncentiveResults:
    """Calculate CACER incentives from explicit energy and finance inputs."""
    region = province_to_region(province, municipalities)
    if region in {
        "Emilia Romagna",
        "Emilia-Romagna",
        "Friuli Venezia Giulia",
        "Friuli-Venezia-Giulia",
        "Liguria",
        "Lombardia",
        "Piemonte",
        "Trentino Alto Adige",
        "Trentino-Alto Adige",
        "Valle d'Aosta",
        "Valle D'Aosta",
        "Veneto",
    }:
        zonal_factor = 10.0
    elif region in {"Lazio", "Marche", "Toscana", "Umbria", "Abruzzo"}:
        zonal_factor = 4.0
    else:
        zonal_factor = 0.0

    pzo = pzo_hourly.rename(columns={"0": "PZO"}).copy()
    pzo.index = pd.DatetimeIndex(pzo.index).strftime("%Y-%m-%d %H")
    pzo.index.name = "dayhour"
    merged = pd.concat(
        [
            shared_energy_hourly.fillna(0),
            valorization_hourly.fillna(0),
            pzo[["PZO"]],
        ],
        axis=1,
        join="inner",
    )
    if len(merged) != len(shared_energy_hourly):
        raise ValueError("PZO and shared-energy indices do not align")

    incentivized = {
        plant: values
        for plant, values in plants.items()
        if bool(values["new_plant"])
    }
    month_numbers = monthly_calendar.set_index("month")["month_number"]
    merged["month"] = merged.index.str[:7]
    merged["month_number"] = merged["month"].map(month_numbers)
    for plant, values in incentivized.items():
        capacity = max(float(values["pv"]), float(values["wind"]))
        if capacity >= 600:
            base, cap = 60.0, 100.0
        elif capacity >= 200:
            base, cap = 70.0, 110.0
        else:
            base, cap = 80.0, 120.0
        grant = float(values["grant_pnrr"])
        grant_factor = 1.0 if grant > 0.4 else (grant / 0.4) * 0.5
        if np.isnan(grant_factor):
            grant_factor = 0.0
        tariff = (
            np.minimum(cap, base + np.maximum(0, 180 - merged["PZO"]))
            + zonal_factor
        ) * (1 - grant_factor)
        if recap["type_of_cacer"] == "NO_CACER":
            tariff = tariff * 0
        tariff = tariff / 1000
        expiration = int(values["commissioning_month"]) + 20 * 12
        tariff = tariff.where(merged["month_number"] <= expiration, 0)
        merged[f"incentivo_{plant}"] = (
            merged[f"Econd_{plant}"] * tariff
        )

    is_auc = recap["type_of_cacer"] == "AUC"
    for configuration in recap["configurations"]:
        merged[f"valorizzazione_config_{configuration}"] = (
            merged[f"Econd_{configuration}_VAL"] * trase / 1000
            + is_auc
            * (
                merged[f"Econd_{configuration}_VAL"] * btau / 1000
                + (
                    merged[f"Econd_bt_{configuration}_VAL"] * cpr_bt
                    + merged[f"Econd_mt_{configuration}_VAL"] * cpr_mt
                )
                * merged["PZO"]
            )
        )
        columns = [
            f"incentivo_{plant}"
            for plant, values in incentivized.items()
            if values["CP"] == configuration
        ]
        merged[f"incentivo_config_{configuration}"] = merged[columns].sum(
            axis=1
        )
    incentive_columns = [
        f"incentivo_config_{value}" for value in recap["configurations"]
    ]
    valorization_columns = [
        f"valorizzazione_config_{value}"
        for value in recap["configurations"]
    ]
    merged["incentivo"] = merged[incentive_columns].sum(axis=1)
    merged["valorizzazione"] = merged[valorization_columns].sum(axis=1)
    by_configuration = merged.groupby("month")[
        incentive_columns
        + valorization_columns
        + ["incentivo", "valorizzazione"]
    ].sum()
    monthly = by_configuration[["incentivo", "valorizzazione"]].copy()
    monthly["incentivo_totale"] = monthly["incentivo"]

    grants = [
        float(values["grant_pnrr"])
        for values in plants.values()
        if not np.isnan(float(values["grant_pnrr"]))
    ]
    max_grant = max([0.0, *grants])
    threshold = 0.55 if max_grant == 0 else 0.45
    yearly = shared_energy_yearly["perc_cond_annuale"].copy()
    yearly.index = yearly.index.astype(str)
    monthly["year"] = monthly.index.str[:4]
    percentages = monthly["year"].map(yearly)
    if not (percentages > threshold).any():
        monthly["surplus"] = 0
    else:
        monthly["surplus"] = monthly["incentivo_totale"] * np.maximum(
            0,
            (percentages - threshold) / percentages,
        ).fillna(0)
    monthly["incentivo"] = monthly["incentivo_totale"] - monthly["surplus"]
    monthly["social_fund"] = 0.0
    if "social_fund" in incentive_repartition:
        shares = incentive_repartition["social_fund"].reindex(monthly.index)
        monthly["social_fund"] += (
            monthly["incentivo"] + monthly["valorizzazione"]
        ) * shares
    if "social_fund" in surplus_repartition:
        shares = surplus_repartition["social_fund"].reindex(monthly.index)
        monthly["social_fund"] += monthly["surplus"] * shares
    monthly = monthly.drop(columns="year")
    monthly.index = monthly_calendar["month_number"].astype(int).to_numpy()
    monthly.index.name = "month_number"
    fees = calculate_cacer_fees(
        users,
        int(recap["total_CACER_members"]),
        cacer_fee_assumptions,
    )
    return IncentiveResults(monthly, by_configuration, fees)


def calculate_cacer_fees(
    users: Mapping[str, Mapping[str, Any]],
    member_count: int,
    assumptions: Mapping[str, Any],
) -> float:
    """Calculate annual fixed and variable GSE CACER fees."""
    total = float(assumptions["var_fees_user"]) * member_count
    for values in users.values():
        capacity = values.get("pv")
        if capacity is None or pd.isna(capacity):
            continue
        capacity = float(capacity)
        if capacity <= 3:
            band = "range_0_3_kw"
        elif capacity <= 20:
            band = "range_3_20_kw"
        else:
            band = "range_20_1000_kw"
        total += float(assumptions["fixed_fees"][band])
        total += float(assumptions["var_fees"][band]) * capacity
    return total
