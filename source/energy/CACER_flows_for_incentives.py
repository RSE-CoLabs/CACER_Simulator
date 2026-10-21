from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd

from source.energy.CACER_flows import ENERGY_COLUMNS


@dataclass(slots=True)
class SharedEnergyResults:
    aggregate_hourly: pd.DataFrame
    incentive_hourly: pd.DataFrame
    incentive_yearly: pd.DataFrame
    valorization_hourly: pd.DataFrame


def CACER_shared_energy_for_TIP(
    user_flows: Mapping[str, pd.DataFrame],
    user_types: Mapping[str, Mapping[str, Any]],
    plants: Mapping[str, Mapping[str, Any]],
    recap: Mapping[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calculate hourly and yearly incentive-eligible shared energy."""
    hourly_index = _hourly_index(user_flows)
    output = pd.DataFrame(index=hourly_index)
    output.index.name = "dayhour"
    output["Eimm_CACER"] = 0.0

    for configuration in recap["configurations"]:
        members = _configuration_members(user_types, configuration)
        consuming = [
            user_id for user_id in members if bool(user_types[user_id]["consuming"])
        ]
        producing = [
            user_id
            for user_id in members
            if bool(user_types[user_id]["producing"])
            and bool(user_types[user_id]["new_plant"])
        ]
        withdrawal = _aggregate_hourly(
            user_flows,
            user_types,
            consuming,
            "Eprel",
        )
        injection_by_type = _hourly_columns(user_flows, producing, "Eimm")
        injection = sum(
            injection_by_type[user_id] * float(user_types[user_id]["num"])
            for user_id in producing
        ) if producing else pd.Series(0.0, index=hourly_index)

        output["Eimm_CACER"] += injection
        config_column = f"Econd_config_{configuration}"
        output[config_column] = pd.concat(
            [withdrawal, injection],
            axis=1,
        ).min(axis=1)
        residual = withdrawal.copy()

        for plant_id in recap["plants_sorted_by_seniority"]:
            plant = plants[plant_id]
            user_id = str(plant["user_type"])
            if user_id not in producing:
                continue
            plant_injection = (
                injection_by_type[user_id] * float(user_types[user_id]["num"])
            )
            shared = pd.concat([residual, plant_injection], axis=1).min(axis=1)
            output[f"Econd_{plant_id}"] = shared
            residual = (residual - shared).clip(lower=0)

    config_columns = [
        column for column in output if column.startswith("Econd_config_")
    ]
    output["Econd_CACER"] = output[config_columns].sum(axis=1)
    if recap["type_of_cacer"] == "NO_CACER":
        output.loc[:, :] = 0.0

    hourly_output = output.mask(output == 0)
    yearly = hourly_output.copy()
    yearly["year"] = yearly.index.str[:4]
    yearly = yearly.groupby("year")[["Eimm_CACER", "Econd_CACER"]].sum()
    yearly["perc_cond_annuale"] = (
        yearly["Econd_CACER"] / yearly["Eimm_CACER"]
    ).fillna(0)
    yearly = yearly.rename(
        columns={"Eimm_CACER": "Eimm", "Econd_CACER": "Econd"}
    )
    yearly.index = yearly.index.astype(int)
    return hourly_output, yearly


def CACER_shared_energy_for_valorization(
    user_flows: Mapping[str, pd.DataFrame],
    user_types: Mapping[str, Mapping[str, Any]],
    recap: Mapping[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calculate hourly CACER totals and TIAD valorization shared energy."""
    hourly_index = _hourly_index(user_flows)
    aggregate = pd.DataFrame(index=hourly_index)
    aggregate.index.name = "dayhour"
    for column in ("Eut", "Eprod", "Eimm", "Eprel", "Eaut", "Eperdite"):
        aggregate[column] = _aggregate_hourly(
            user_flows,
            user_types,
            list(user_types),
            column,
        )

    valorization = pd.DataFrame(index=hourly_index)
    valorization.index.name = "dayhour"
    valorization["Econd_VAL"] = 0.0
    valorization["Econd_bt_VAL"] = 0.0
    valorization["Econd_mt_VAL"] = 0.0

    for configuration in recap["configurations"]:
        members = _configuration_members(user_types, configuration)
        consuming = [
            user_id for user_id in members if bool(user_types[user_id]["consuming"])
        ]
        producing = [
            user_id for user_id in members if bool(user_types[user_id]["producing"])
        ]
        withdrawn = _aggregate_hourly(
            user_flows,
            user_types,
            consuming,
            "Eprel",
        )
        injected = _aggregate_hourly(
            user_flows,
            user_types,
            producing,
            "Eimm",
        )
        shared = pd.concat([withdrawn, injected], axis=1).min(axis=1)

        low_voltage = [
            user_id
            for user_id in members
            if str(user_types[user_id]["voltage"]) != "MT"
        ]
        medium_voltage = [
            user_id
            for user_id in members
            if str(user_types[user_id]["voltage"]) == "MT"
        ]
        low_withdrawn = _aggregate_hourly(
            user_flows, user_types, low_voltage, "Eprel"
        )
        low_injected = _aggregate_hourly(
            user_flows, user_types, low_voltage, "Eimm"
        )
        medium_withdrawn = _aggregate_hourly(
            user_flows, user_types, medium_voltage, "Eprel"
        )
        medium_injected = _aggregate_hourly(
            user_flows, user_types, medium_voltage, "Eimm"
        )
        low_shared = pd.concat(
            [low_withdrawn, low_injected],
            axis=1,
        ).min(axis=1)
        medium_shared = pd.concat(
            [medium_withdrawn, medium_injected],
            axis=1,
        ).min(axis=1)

        valorization[f"Econd_{configuration}_VAL"] = shared
        valorization[f"Econd_bt_{configuration}_VAL"] = low_shared
        valorization[f"Econd_mt_{configuration}_VAL"] = medium_shared
        valorization["Econd_VAL"] += shared
        valorization["Econd_bt_VAL"] += low_shared
        valorization["Econd_mt_VAL"] += medium_shared

    aggregate["Econd"] = valorization["Econd_VAL"]
    if recap["type_of_cacer"] == "NO_CACER":
        aggregate["Econd"] = 0.0
        valorization.loc[:, :] = 0.0
    return aggregate, valorization


def CACER_shared_energy(
    user_flows: Mapping[str, pd.DataFrame],
    user_types: Mapping[str, Mapping[str, Any]],
    plants: Mapping[str, Mapping[str, Any]],
    recap: Mapping[str, Any],
) -> SharedEnergyResults:
    """Calculate all aggregate, shared, and incentive-eligible energy tables."""
    incentive_hourly, incentive_yearly = CACER_shared_energy_for_TIP(
        user_flows,
        user_types,
        plants,
        recap,
    )
    aggregate_hourly, valorization_hourly = (
        CACER_shared_energy_for_valorization(
            user_flows,
            user_types,
            recap,
        )
    )
    return SharedEnergyResults(
        aggregate_hourly=aggregate_hourly,
        incentive_hourly=incentive_hourly,
        incentive_yearly=incentive_yearly,
        valorization_hourly=valorization_hourly,
    )


def _configuration_members(
    user_types: Mapping[str, Mapping[str, Any]],
    configuration: str,
) -> list[str]:
    return [
        user_id
        for user_id, values in user_types.items()
        if values["CP"] == configuration
        and float(values["num"]) > 0
        and bool(values["flag_cacer"])
    ]


def _hourly_columns(
    user_flows: Mapping[str, pd.DataFrame],
    users: list[str],
    column: str,
) -> pd.DataFrame:
    index = _hourly_index(user_flows)
    result = pd.DataFrame(index=index)
    for user_id in users:
        series = user_flows[user_id][column].fillna(0).astype(float).copy()
        series.index = pd.to_datetime(series.index)
        result[user_id] = series.resample("h").sum().to_numpy()
    return result


def _aggregate_hourly(
    user_flows: Mapping[str, pd.DataFrame],
    user_types: Mapping[str, Mapping[str, Any]],
    users: list[str],
    column: str,
) -> pd.Series:
    index = _hourly_index(user_flows)
    if not users:
        return pd.Series(0.0, index=index)
    columns = _hourly_columns(user_flows, users, column)
    quantities = pd.Series(
        {user_id: float(user_types[user_id]["num"]) for user_id in users}
    )
    return columns.mul(quantities, axis=1).sum(axis=1)


def _hourly_index(
    user_flows: Mapping[str, pd.DataFrame],
) -> pd.Index:
    first = next(iter(user_flows.values()))
    index = pd.to_datetime(first.index).floor("h").unique()
    return pd.Index(index.strftime("%Y-%m-%d %H"), name="dayhour")
