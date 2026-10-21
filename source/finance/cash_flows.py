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
from source.data_structures import (
    BillingResults,
    CashFlowResults,
    FinancialIndicators,
    IncentiveResults,
    OwnershipResults,
    RidResults,
)


def build_finance_template(
    monthly_calendar: pd.DataFrame,
    inflation: pd.Series,
    discount_rates: Mapping[str, float],
) -> pd.DataFrame:
    """Build monthly inflation and category discount factors."""
    frame = monthly_calendar[["month", "month_number"]].copy()
    frame["year"] = frame["month"].str[:4]
    annual = inflation.copy()
    annual.index = annual.index.astype(int).astype(str)
    factor = 1.0
    factors = []
    for index, year in enumerate(frame["year"]):
        monthly_rate = (1 + float(annual.loc[year])) ** (1 / 12) - 1
        if index:
            factor *= 1 + monthly_rate
        factors.append(factor)
    frame["inflation_factor"] = factors
    for category, rate in discount_rates.items():
        monthly_rate = (1 + float(rate)) ** (1 / 12) - 1
        frame[f"discount_factor_{category}"] = 1 / (
            (1 + monthly_rate) ** (frame["month_number"] - 1)
        )
    result = frame.set_index("month_number").drop(columns="year")
    result.index.name = None
    return result


def calculate_cash_flows(
    *,
    template: pd.DataFrame,
    users: Mapping[str, Mapping[str, Any]],
    plants: Mapping[str, Mapping[str, Any]],
    recap: Mapping[str, Any],
    ownership: OwnershipResults,
    bills: BillingResults,
    rid: RidResults,
    incentives: IncentiveResults,
    user_entry_matrix: pd.DataFrame,
    membership_matrix: pd.DataFrame,
    plant_operation_matrix: pd.DataFrame,
    capex_table: pd.DataFrame,
    opex_plant: pd.Series,
    opex_cacer: pd.Series,
    taxes: pd.DataFrame,
    active_cacer_kickoff: float,
    entry_fee: float,
    subscription_fee: float,
    ground_opex_factor: float,
) -> tuple[CashFlowResults, FinancialIndicators]:
    """Calculate plant, user, and project cash flows without file coupling."""
    plant_tables: dict[str, dict[str, pd.DataFrame]] = {}
    for plant, values in plants.items():
        plant_tables[plant] = _plant_cash_flow(
            template,
            values,
            ownership.plant_capex[plant],
            rid,
            plant_operation_matrix.loc[plant].astype(float),
            capex_table,
            opex_plant,
            ground_opex_factor,
        )

    user_tables: dict[str, dict[str, pd.DataFrame]] = {}
    for user, values in users.items():
        if values["dummy_user"]:
            continue
        owned: dict[str, pd.DataFrame] = {}
        totals = _totals_template(template, str(values["category"]))
        for plant, tables in plant_tables.items():
            share = ownership.investment.loc[user, plant]
            if pd.isna(share) or not share:
                continue
            detail = _combine_plant_detail(tables) * float(share)
            detail.insert(0, "month", template["month"])
            if plants[plant]["titolare_POD"] == user:
                user_type = plants[plant]["user_type"]
                detail["revenues_electricity_savings"] = (
                    bills.user_bills[user_type]["bau"]["total_bill_cost"]
                    - bills.user_bills[user_type]["pv"]["total_bill_cost"]
                ).to_numpy() * (
                    membership_matrix.loc[user].astype(float).to_numpy()
                ) * (
                    plant_operation_matrix.loc[plant].astype(float).to_numpy()
                ) * template["inflation_factor"].to_numpy()
            else:
                detail["revenues_electricity_savings"] = 0.0
            detail["revenues_condominium_electricity_savings"] = 0.0
            owned[plant] = detail
            _add_detail_to_totals(totals, detail)
        cacer = _user_cacer_flows(
            user,
            template,
            values,
            recap,
            ownership,
            incentives,
            user_entry_matrix,
            active_cacer_kickoff,
            entry_fee,
            subscription_fee,
            opex_cacer,
        )
        _add_detail_to_totals(totals, cacer)
        dcf, yearly, result = _dcf(
            totals,
            user,
            str(values["category"]),
            taxes,
            non_taxable=sum(
                (
                    table["revenues_electricity_savings"]
                    for table in owned.values()
                ),
                start=pd.Series(0.0, index=template.index),
            ),
        )
        user_tables[user] = {
            **owned,
            "CACER": cacer,
            "totals": totals,
            "DCF_monthly": dcf,
            "DCF_yearly": yearly,
            "Results": result.T,
        }

    cacer_totals = _totals_template(template, "CACER")
    cacer_detail = _cacer_entity_flows(
        template,
        recap,
        ownership,
        incentives,
        user_entry_matrix,
        entry_fee,
        subscription_fee,
        opex_cacer,
    )
    _add_detail_to_totals(cacer_totals, cacer_detail)
    dcf, yearly, result = _dcf(
        cacer_totals,
        "CACER",
        "CACER",
        taxes,
    )
    user_tables["CACER"] = {
        "CACER": cacer_detail,
        "totals": cacer_totals,
        "DCF_monthly": dcf,
        "DCF_yearly": yearly,
        "Results": result.T,
    }
    social = template[["month", "inflation_factor"]].copy()
    social["revenues_social_fund"] = (
        incentives.monthly["social_fund"].to_numpy()
        * social["inflation_factor"]
    )
    user_tables["social_fund"] = {"CACER": social}

    groups: dict[str, dict[str, pd.DataFrame]] = {}
    for group in [*recap["configurations"], "project"]:
        members = [
            user
            for user, values in users.items()
            if not values["dummy_user"]
            and (group == "project" or values["CP"] == group)
        ]
        if group == "project":
            members.append("CACER")
        groups[group] = _aggregate_group(user_tables, members, group, taxes)
    project = groups["project"]
    indicators = FinancialIndicators(
        project["DCF_monthly"],
        project["DCF_yearly"],
        float(project["Results"].loc["project", "NPV"]),
        float(project["Results"].loc["project", "IRR"]),
        float(project["Results"].loc["project", "Payback Period"]),
    )
    return (
        CashFlowResults(
            plants=plant_tables,
            users=user_tables,
            configurations={
                key: value for key, value in groups.items() if key != "project"
            },
            project=project,
        ),
        indicators,
    )


def _plant_cash_flow(
    template: pd.DataFrame,
    plant: Mapping[str, Any],
    capex_values: Mapping[str, float],
    rid: RidResults,
    operation: pd.Series,
    capex_table: pd.DataFrame,
    opex_inputs: pd.Series,
    ground_factor: float,
) -> dict[str, pd.DataFrame]:
    index = template.index
    months = template["month"]
    capex_columns = [
        "capex_pv", "capex_pv_inverter", "capex_battery", "capex_wind",
        "capex_mv_cabinet", "capex_grant_pnrr", "capex_grant_private",
        "capex_replacement_battery", "capex_replacement_pv_inverter",
    ]
    da_columns = [name.replace("capex_", "da_") for name in capex_columns]
    capex = pd.DataFrame(0.0, index=index, columns=capex_columns)
    da = pd.DataFrame(0.0, index=index, columns=da_columns)
    disbursement = int(plant["disbursement_month"])
    commissioning = int(plant["commissioning_month"])
    total = 0.0
    for item in ("pv", "pv_inverter", "battery", "wind", "mv_cabinet"):
        value = -float(capex_values[f"capex_{item}"]) * template.loc[
            disbursement, "inflation_factor"
        ]
        if item == "pv" and plant["pv_mounting"] == "ground":
            value *= ground_factor
        capex.loc[disbursement, f"capex_{item}"] = value
        total += value
        months_da = int(
            min(
                float(capex_table.loc["amortization", item]) * 12,
                len(index) - commissioning,
            )
        )
        if months_da:
            active = (index >= disbursement) & (
                index < disbursement + months_da
            )
            da.loc[active, f"da_{item}"] = value / months_da
    for grant in ("grant_pnrr", "grant_private"):
        value = -float(plant[grant]) * total
        capex.loc[disbursement, f"capex_{grant}"] = value
        months_da = int(
            min(
                float(capex_table.loc["amortization", "pv"]) * 12,
                len(index) - disbursement,
            )
        )
        if months_da:
            da.loc[
                (index >= disbursement) & (index < disbursement + months_da),
                f"da_{grant}",
            ] = value / months_da
    debt_index = pd.RangeIndex(1, 74)
    debt = pd.DataFrame(
        0.0,
        index=debt_index,
        columns=[
            "debt_interest", "debt_principal", "debt_disbursment",
            "debt_payment", "debt_ending_balance",
            "debt_disbursment/payment", "debt_beginning_balance",
        ],
    )
    debt.insert(
        0,
        "month",
        [*months.tolist(), *([0] * (len(debt_index) - len(months)))],
    )
    active = operation.to_numpy()
    inflation = template["inflation_factor"].to_numpy()
    opex = pd.DataFrame(index=index)
    subtotal = np.zeros(len(index))
    for item in ("pv", "battery", "wind", "mv_cabinet"):
        if item == "mv_cabinet" and not bool(plant[item]):
            continue
        size = float(plant[item] or 0)
        if item == "mv_cabinet":
            size = max(float(plant["pv"]), float(plant["wind"])) * bool(
                plant[item]
            )
        unit = float(opex_inputs[item])
        if item == "pv" and plant["pv_mounting"] == "ground":
            unit *= ground_factor
        values = -active * inflation * size * unit / 12
        opex[f"opex_{item}"] = values
        subtotal += values
    insurance = active * inflation * total * float(
        opex_inputs["asset_insurance"]
    ) / 12
    opex["opex_asset_insurance"] = insurance
    subtotal += insurance
    user_type = str(plant["user_type"])
    rid_fee = -active * inflation * float(
        rid.gse_fees.loc["GSE_fees", user_type]
    ) / 12
    opex["opex_rid_GSE_fees"] = rid_fee
    subtotal += rid_fee
    contingency = (
        active
        * inflation
        * subtotal
        * float(opex_inputs["contingency"])
        / 12
    )
    opex["opex_contingency"] = contingency
    revenues = pd.DataFrame(
        {
            "revenues_rid": (
                rid.monthly_revenue[user_type].to_numpy() * inflation
            )
        },
        index=index,
    )
    totals = pd.DataFrame(
        {
            "month": months,
            "capex_total": capex.sum(axis=1),
            "da_total": da.sum(axis=1),
            "debt_interest": debt.loc[index, "debt_interest"],
            "opex_total": opex.sum(axis=1),
            "revenues_total": revenues.sum(axis=1),
        },
        index=index,
    )
    return {
        "Capex": pd.concat([months, capex], axis=1),
        "D&A": pd.concat([months, da], axis=1),
        "Debt": debt,
        "Opex": pd.concat([months, opex], axis=1),
        "Revenues": pd.concat([months, revenues], axis=1),
        "Totals": totals,
    }


def _combine_plant_detail(
    tables: Mapping[str, pd.DataFrame],
) -> pd.DataFrame:
    index = tables["Totals"].index
    return pd.concat(
        [
            tables["Capex"].drop(columns="month").reindex(index),
            tables["D&A"].drop(columns="month").reindex(index),
            tables["Debt"].drop(columns="month").reindex(index),
            tables["Opex"].drop(columns="month").reindex(index),
            tables["Revenues"].drop(columns="month").reindex(index),
        ],
        axis=1,
    )


def _totals_template(template: pd.DataFrame, category: str) -> pd.DataFrame:
    result = template[["month", "inflation_factor"]].copy()
    result["discount_factor"] = template[f"discount_factor_{category}"]
    for column in (
        "capex_total", "da_total", "debt_interest",
        "opex_total", "revenues_total",
    ):
        result[column] = 0.0
    return result


def _add_detail_to_totals(
    totals: pd.DataFrame,
    detail: pd.DataFrame,
) -> None:
    totals["capex_total"] += detail[
        [column for column in detail if column.startswith("capex_")]
    ].sum(axis=1)
    totals["da_total"] += detail[
        [column for column in detail if column.startswith("da_")]
    ].sum(axis=1)
    totals["debt_interest"] += detail.get("debt_interest", 0)
    totals["opex_total"] += detail[
        [column for column in detail if column.startswith("opex_")]
    ].sum(axis=1)
    totals["revenues_total"] += detail[
        [column for column in detail if column.startswith("revenues_")]
    ].sum(axis=1)


def _user_cacer_flows(
    user: str,
    template: pd.DataFrame,
    user_values: Mapping[str, Any],
    recap: Mapping[str, Any],
    ownership: OwnershipResults,
    incentives: IncentiveResults,
    entry_matrix: pd.DataFrame,
    kickoff: float,
    entry_fee: float,
    subscription_fee: float,
    opex_cacer: pd.Series,
) -> pd.DataFrame:
    frame = template[["month", "inflation_factor"]].copy()
    inflation = frame["inflation_factor"]
    entries = entry_matrix.loc[user].astype(float)
    frame["capex_entry_fee"] = -abs(entry_fee) * entries * inflation
    frame["capex_cacer_kickoff"] = 0.0
    present = [
        value
        for value in recap["users_present_month_1"]
        if value in entry_matrix.index
    ]
    frame.loc[1, "capex_cacer_kickoff"] = -abs(kickoff) / len(present)
    shares = ownership.repartition["incentives"].loc[user].astype(float)
    surplus_shares = ownership.repartition["surplus"].loc[user].astype(float)
    frame["revenues_incentives"] = (
        incentives.monthly["incentivo"].to_numpy() * shares
    )
    frame["revenues_valorization"] = (
        incentives.monthly["valorizzazione"].to_numpy() * shares * inflation
    )
    frame["revenues_surplus"] = (
        incentives.monthly["surplus"].to_numpy()
        * surplus_shares
    )
    subscription = ownership.subscription.loc[user].astype(float)
    frame["opex_subscription_fee"] = (
        -abs(subscription_fee) * subscription * inflation
    )
    opex_shares = ownership.repartition["CACER opex"].loc[user].astype(float)
    frame["opex_CACER_GSE_fees"] = (
        -float(opex_cacer["CACER_GSE_fees_per_configuration"])
        / 12
        * opex_shares
        * inflation
    )
    frame["opex_administration"] = (
        -float(opex_cacer["administration"])
        / 12
        * opex_shares
        * inflation
    )
    frame["opex_cacer_management_platform"] = (
        -(
            float(opex_cacer["cacer_management_platform_fixed"])
            + float(opex_cacer["cacer_management_platform_variable"])
            * int(recap["total_CACER_members"])
        )
        / 12
        * opex_shares
        * inflation
    )
    return frame


def _cacer_entity_flows(
    template: pd.DataFrame,
    recap: Mapping[str, Any],
    ownership: OwnershipResults,
    incentives: IncentiveResults,
    entry_matrix: pd.DataFrame,
    entry_fee: float,
    subscription_fee: float,
    opex_cacer: pd.Series,
) -> pd.DataFrame:
    frame = template[["month", "inflation_factor"]].copy()
    inflation = frame["inflation_factor"]
    frame["revenues_entry_fee"] = (
        abs(entry_fee) * entry_matrix.astype(float).sum(axis=0) * inflation
    )
    frame["capex_cacer_kickoff"] = 0.0
    incentive_shares = ownership.repartition["incentives"].loc[
        "CACER"
    ].astype(float)
    frame["revenues_incentives_from_GSE"] = incentives.monthly[
        "incentivo"
    ].to_numpy()
    frame["opex_incentives_repartition"] = (
        -frame["revenues_incentives_from_GSE"] * (1 - incentive_shares)
    )
    frame["revenues_valorization_from_GSE"] = (
        incentives.monthly["valorizzazione"].to_numpy() * inflation
    )
    frame["opex_valorization_repartition"] = (
        -frame["revenues_valorization_from_GSE"] * (1 - incentive_shares)
    )
    surplus_shares = ownership.repartition["surplus"].loc["CACER"].astype(float)
    frame["revenues_surplus_from_GSE"] = incentives.monthly[
        "surplus"
    ].to_numpy()
    frame["opex_surplus_redistribution"] = (
        -frame["revenues_surplus_from_GSE"] * (1 - surplus_shares)
    )
    frame["revenues_subscription_fee"] = (
        abs(subscription_fee)
        * ownership.subscription.astype(float).sum(axis=0)
        * inflation
    )
    opex_shares = ownership.repartition["CACER opex"].loc["CACER"].astype(float)
    frame["opex_CACER_GSE_fees"] = (
        -float(opex_cacer["CACER_GSE_fees_per_configuration"])
        / 12
        * opex_shares
        * inflation
    )
    frame["opex_administration"] = (
        -float(opex_cacer["administration"])
        / 12
        * opex_shares
        * inflation
    )
    frame["opex_cacer_management_platform"] = -(
        float(opex_cacer["cacer_management_platform_fixed"])
        + float(opex_cacer["cacer_management_platform_variable"])
        * int(recap["total_CACER_members"])
    ) / 12 * opex_shares * inflation
    return frame


def _dcf(
    totals: pd.DataFrame,
    name: str,
    category: str,
    taxes: pd.DataFrame,
    *,
    non_taxable: pd.Series | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frame = totals.copy()
    frame["revenues_total_taxable"] = frame["revenues_total"]
    if non_taxable is not None:
        frame["revenues_total_taxable"] -= non_taxable.to_numpy()
    frame["EBITDA"] = frame["revenues_total_taxable"] + frame["opex_total"]
    frame["EBIT"] = frame["EBITDA"] + frame["da_total"]
    frame["PBT"] = frame["EBIT"] + frame["debt_interest"]
    ires = float(taxes.loc["ires", "Value"]) * bool(
        taxes.loc["ires", category]
    )
    irap = float(taxes.loc["irap", "Value"]) * bool(
        taxes.loc["irap", category]
    )
    frame["taxes_ires"] = -frame["PBT"] * ires * (frame["PBT"] > 0)
    frame["taxes_irap"] = -frame["PBT"] * irap * (frame["PBT"] > 0)
    frame["taxes_total"] = frame["taxes_ires"] + frame["taxes_irap"]
    frame["Net Earnings"] = frame["PBT"] + frame["taxes_total"]
    frame["Net Final Earnings"] = frame["Net Earnings"] + (
        frame["revenues_total"] - frame["revenues_total_taxable"]
    )
    frame["FCF"] = frame[
        [
            "capex_total", "opex_total", "revenues_total",
            "taxes_total", "debt_interest",
        ]
    ].sum(axis=1)
    frame["FCF_cum"] = frame["FCF"].cumsum()
    frame["DCF"] = frame["FCF"] * frame["discount_factor"]
    frame["DCF_cum"] = frame["DCF"].cumsum()
    yearly_source = frame.copy()
    yearly_source["year"] = yearly_source["month"].str[:4]
    yearly = yearly_source.drop(
        columns=[
            "month", "inflation_factor", "discount_factor",
            "FCF_cum", "DCF_cum",
        ]
    ).groupby("year").sum()
    yearly["FCF_cum"] = yearly["FCF"].cumsum()
    yearly["DCF_cum"] = yearly["DCF"].cumsum()
    yearly = yearly.reset_index()
    yearly["year"] = pd.to_numeric(yearly["year"])
    yearly.index += 1
    irr = float(npf.irr(yearly["FCF"].to_numpy()))
    npv = float(frame["DCF_cum"].iloc[-1])
    negative = frame[frame["DCF_cum"] < 0]
    final_month = int(negative.index.max()) if not negative.empty else int(
        frame.index.max()
    )
    if final_month == int(frame.index.max()):
        payback = final_month / 12
    else:
        delta = frame.loc[final_month + 1, "DCF_cum"] - frame.loc[
            final_month, "DCF_cum"
        ]
        payback = (
            final_month + abs(frame.loc[final_month, "DCF_cum"] / delta)
        ) / 12
    result = pd.DataFrame(
        {name: [irr, npv, payback]},
        index=["IRR", "NPV", "Payback Period"],
    )
    return frame, yearly, result


def _aggregate_group(
    user_tables: Mapping[str, Mapping[str, pd.DataFrame]],
    members: list[str],
    name: str,
    taxes: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    totals = sum(
        (
            user_tables[member]["totals"][
                [
                    "capex_total", "da_total", "debt_interest",
                    "opex_total", "revenues_total",
                ]
            ]
            for member in members
        ),
        start=pd.DataFrame(
            0.0,
            index=user_tables[members[0]]["totals"].index,
            columns=[
                "capex_total", "da_total", "debt_interest",
                "opex_total", "revenues_total",
            ],
        ),
    )
    template = user_tables[members[0]]["totals"]
    totals.insert(0, "discount_factor", template["discount_factor"])
    totals.insert(0, "inflation_factor", template["inflation_factor"])
    totals.insert(0, "month", template["month"])
    non_taxable = sum(
        (
            table["revenues_electricity_savings"]
            for member in members
            for key, table in user_tables[member].items()
            if key not in {"CACER", "totals", "DCF_monthly", "DCF_yearly", "Results"}
            and "revenues_electricity_savings" in table
        ),
        start=pd.Series(0.0, index=totals.index),
    )
    dcf, yearly, result = _dcf(
        totals, name, "CACER", taxes, non_taxable=non_taxable
    )
    plant_details = {}
    cacer_details = {}
    for member in members:
        for key, table in user_tables[member].items():
            if key in {"totals", "DCF_monthly", "DCF_yearly", "Results"}:
                continue
            target = cacer_details if key == "CACER" else plant_details
            numeric = table.drop(columns=["month"], errors="ignore")
            if key in target:
                target[key] = target[key].add(numeric, fill_value=0)
            else:
                target[key] = numeric.copy()
    plants = (
        pd.concat(plant_details.values(), axis=1)
        .T.groupby(level=0, sort=False).sum().T
        if plant_details
        else pd.DataFrame(index=totals.index)
    )
    cacer = (
        pd.concat(cacer_details.values(), axis=1)
        .T.groupby(level=0, sort=False).sum().T
        if cacer_details
        else pd.DataFrame(index=totals.index)
    )
    cacer = cacer.drop(columns="inflation_factor", errors="ignore")
    cacer_entity_columns = [
        "revenues_entry_fee",
        "capex_cacer_kickoff",
        "revenues_incentives_from_GSE",
        "opex_incentives_repartition",
        "revenues_valorization_from_GSE",
        "opex_valorization_repartition",
        "revenues_surplus_from_GSE",
        "opex_surplus_redistribution",
        "revenues_subscription_fee",
        "opex_CACER_GSE_fees",
        "opex_administration",
        "opex_cacer_management_platform",
    ]
    cacer_user_columns = [
        "capex_entry_fee",
        "revenues_incentives",
        "revenues_valorization",
        "revenues_surplus",
        "opex_subscription_fee",
    ]
    if "CACER" in members:
        cacer_order = cacer_entity_columns + cacer_user_columns
    else:
        cacer_order = [
            "capex_entry_fee",
            "capex_cacer_kickoff",
            "revenues_incentives",
            "revenues_valorization",
            "revenues_surplus",
            "opex_subscription_fee",
            "opex_CACER_GSE_fees",
            "opex_administration",
            "opex_cacer_management_platform",
        ]
    cacer = cacer[
        [column for column in cacer_order if column in cacer]
        + [column for column in cacer if column not in cacer_order]
    ]
    group_dcf = dcf.drop(
        columns=[
            "month",
            "inflation_factor",
            "discount_factor",
            "EBITDA",
            "EBIT",
            "PBT",
        ]
    )
    group_dcf = group_dcf[
        [
            "capex_total",
            "da_total",
            "debt_interest",
            "opex_total",
            "revenues_total",
            "revenues_total_taxable",
            "taxes_ires",
            "taxes_irap",
            "taxes_total",
            "Net Earnings",
            "Net Final Earnings",
            "FCF",
            "DCF",
            "FCF_cum",
            "DCF_cum",
        ]
    ]
    group_yearly = yearly.drop(columns=["EBITDA", "EBIT", "PBT"])[
        [
            "year",
            "capex_total",
            "da_total",
            "debt_interest",
            "opex_total",
            "revenues_total",
            "revenues_total_taxable",
            "taxes_ires",
            "taxes_irap",
            "taxes_total",
            "Net Earnings",
            "Net Final Earnings",
            "FCF",
            "DCF",
            "FCF_cum",
            "DCF_cum",
        ]
    ]
    group_yearly["year"] = (
        pd.to_numeric(group_yearly["year"]) * len(members)
    )
    return {
        "plants": plants,
        "CACER": cacer,
        "totals": totals[
            [
                "capex_total", "da_total", "debt_interest",
                "opex_total", "revenues_total",
            ]
        ],
        "DCF_monthly": group_dcf,
        "DCF_yearly": group_yearly,
        "Results": result.T,
    }
