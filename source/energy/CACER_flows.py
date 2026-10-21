from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from source.energy.battery_management import BESS


ENERGY_COLUMNS = (
    "Eut",
    "Eprod",
    "Eaut",
    "Eprel",
    "Eimm",
    "Eperdite",
    "Eaut_PV",
    "Eaut_batt",
)


@dataclass(slots=True)
class BatteryState:
    cumulative_charge_kwh: float
    soc_kwh: float


def mergedict(a: dict[Any, Any], b: Mapping[Any, Any]) -> dict[Any, Any]:
    """Preserve the legacy in-place dictionary merge."""
    a.update(b)
    return a


def simulate_timestep_single_user(
    load_kwh: float,
    production_kwh: float,
    user_values: Mapping[str, Any],
    battery_state: BatteryState,
    *,
    dod: float,
    round_trip_efficiency: float,
    battery_derating_factor: float,
) -> tuple[dict[str, float], BatteryState]:
    """Calculate one user's energy balance for one simulation interval."""
    user_type = str(user_values["type"])
    consumption = load_kwh if user_type in {"consumer", "prosumer"} else 0.0
    production = (
        max(production_kwh, 0.0)
        if user_type in {"producer", "prosumer"}
        else 0.0
    )
    battery_capacity = float(user_values.get("battery") or 0.0)

    terminal_flow = losses = discharge_net = soc_kwh = soc_percent = 0.0
    cumulative_charge = battery_state.cumulative_charge_kwh
    if battery_capacity > 0:
        cycle_count = cumulative_charge / (battery_capacity * dod)
        derating_index = (1 - battery_derating_factor) ** cycle_count
        maximum = derating_index * battery_capacity
        minimum = maximum * (1 - dod)
        terminal_flow, losses, discharge_net, soc_kwh, soc_percent = BESS(
            production - consumption,
            battery_state.soc_kwh,
            np.sqrt(round_trip_efficiency),
            minimum,
            maximum,
        )
        if terminal_flow > 0:
            cumulative_charge += soc_kwh - battery_state.soc_kwh

    direct_self_consumption = min(production, consumption)
    battery_self_consumption = (
        min(-discharge_net, consumption - direct_self_consumption)
        if battery_capacity > 0
        else 0.0
    )
    self_consumption = direct_self_consumption + battery_self_consumption
    grid_exchange = production - consumption - terminal_flow
    withdrawn = -min(0.0, grid_exchange)
    injected = max(0.0, grid_exchange)

    values = {
        "Eut": consumption,
        "Eprod": production,
        "Eaut_PV": direct_self_consumption,
        "Eaut_batt": battery_self_consumption,
        "Eaut": self_consumption,
        "battery_cumulative_charge": cumulative_charge,
        "SOCkWh": soc_kwh,
        "SOCperc": soc_percent,
        "Eperdite": losses,
        "Eprel": withdrawn,
        "Eimm": injected,
        "LCF_aut": (
            self_consumption / consumption
            if user_type == "prosumer" and self_consumption > 1e-4 and consumption
            else 0.0
        ),
        "SCF_aut": (
            self_consumption / production
            if user_type == "prosumer" and self_consumption > 1e-4 and production
            else 0.0
        ),
    }
    return values, BatteryState(cumulative_charge, soc_kwh)


def CACER_energy_flows(
    load_profiles: pd.DataFrame,
    generation_profiles: pd.DataFrame,
    user_types: Mapping[str, Mapping[str, Any]],
    plant_type_operation: pd.DataFrame,
    *,
    dod: float,
    round_trip_efficiency: float,
    battery_derating_factor: float,
    battery_enabled: bool = True,
) -> dict[str, pd.DataFrame]:
    """Calculate per-user-type flows without intermediate file exchange."""
    loads = _with_datetime_index(load_profiles)
    generation = _with_datetime_index(generation_profiles)
    generation = generation.reindex(loads.index).fillna(0.0)
    operation = _operation_by_datetime(loads.index, plant_type_operation)
    results: dict[str, pd.DataFrame] = {}

    for user_id, values in user_types.items():
        user_type = str(values["type"])
        load = (
            loads[user_id].astype(float)
            if user_type in {"consumer", "prosumer"} and user_id in loads
            else pd.Series(0.0, index=loads.index)
        )
        production = (
            generation[user_id].astype(float)
            if user_type in {"producer", "prosumer"} and user_id in generation
            else pd.Series(0.0, index=loads.index)
        )
        if user_id in operation:
            production = production * operation[user_id]

        battery_capacity = (
            float(values.get("battery") or 0.0) if battery_enabled else 0.0
        )
        effective_values = dict(values)
        effective_values["battery"] = battery_capacity
        if battery_capacity <= 0:
            frame = _vectorized_flows(load, production, user_type)
        else:
            state = BatteryState(0.0, battery_capacity * (1 - dod))
            rows: list[dict[str, float]] = []
            for timestamp in loads.index:
                row, state = simulate_timestep_single_user(
                    float(load.loc[timestamp]),
                    float(production.loc[timestamp]),
                    effective_values,
                    state,
                    dod=dod,
                    round_trip_efficiency=round_trip_efficiency,
                    battery_derating_factor=battery_derating_factor,
                )
                rows.append(row)
            frame = pd.DataFrame(rows, index=loads.index)

        frame.index.name = "datetime"
        results[user_id] = frame
    return results


def import_users_energy_flows(
    user_type_set: Sequence[str],
    user_flows: Mapping[str, pd.DataFrame],
) -> pd.DataFrame:
    """Return the legacy stacked multi-user representation in memory."""
    frames = []
    for user_id in user_type_set:
        frame = user_flows[user_id].copy().fillna(0)
        frame["user"] = user_id
        frame["datetime"] = frame.index.astype(str)
        frames.append(frame.reset_index(drop=True))
    if not frames:
        return pd.DataFrame(columns=[*ENERGY_COLUMNS, "user", "datetime"])
    return pd.concat(frames, ignore_index=True)


def import_users_energy_flow_single_column(
    user_type_set: Sequence[str],
    energy_column: str,
    user_flows: Mapping[str, pd.DataFrame],
) -> pd.DataFrame:
    """Collect one flow column for selected user types."""
    if not user_type_set:
        index = next(iter(user_flows.values())).index
        return pd.DataFrame(index=index.astype(str))
    result = pd.DataFrame(
        {
            user_id: user_flows[user_id][energy_column].fillna(0).astype(float)
            for user_id in user_type_set
        }
    )
    result.index = result.index.astype(str)
    result.index.name = "datetime"
    return result


def export_energy_exchange_profiles_csv(
    user_flows: Mapping[str, pd.DataFrame],
) -> pd.DataFrame:
    """Create the per-user exchange table formerly written by the legacy helper."""
    return pd.concat(
        {
            user_id: frame[["Eprel", "Eimm"]].fillna(0)
            for user_id, frame in user_flows.items()
        },
        axis=1,
    )


def CACER_injected_energy_optimizer(
    user_flows: Mapping[str, pd.DataFrame],
    user_types: Mapping[str, Mapping[str, Any]],
) -> pd.DataFrame:
    """Aggregate injected energy for the optional DSM optimizer."""
    producers = [
        user_id
        for user_id, values in user_types.items()
        if bool(values["producing"])
    ]
    injected = import_users_energy_flow_single_column(
        producers,
        "Eimm",
        user_flows,
    )
    quantities = pd.Series(
        {user_id: float(user_types[user_id]["num"]) for user_id in producers}
    )
    result = pd.DataFrame(index=injected.index)
    result["Enet_inj_config"] = injected.mul(quantities, axis=1).sum(axis=1)
    return result


def _vectorized_flows(
    load: pd.Series,
    production: pd.Series,
    user_type: str,
) -> pd.DataFrame:
    frame = pd.DataFrame(index=load.index)
    if user_type == "consumer":
        frame["Eprel"] = load
        frame["Eut"] = load
        for column in (
            "Eimm",
            "Eprod",
            "Eperdite",
            "Eaut",
            "Eaut_PV",
            "Eaut_batt",
        ):
            frame[column] = np.nan
        return frame
    if user_type == "producer":
        frame["Eprod"] = production
        frame["Eimm"] = production
        for column in (
            "Eut",
            "Eperdite",
            "Eprel",
            "Eaut",
            "Eaut_PV",
            "Eaut_batt",
        ):
            frame[column] = np.nan
        return frame

    frame["Eut"] = load
    frame["Eprod"] = production
    frame["Eaut"] = np.minimum(frame["Eut"], frame["Eprod"])
    frame["Eprel"] = frame["Eut"] - frame["Eaut"]
    frame["Eimm"] = frame["Eprod"] - frame["Eaut"]
    frame["Eperdite"] = np.nan
    frame["Eaut_PV"] = frame["Eaut"]
    frame["Eaut_batt"] = np.nan
    return frame


def _with_datetime_index(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "datetime" in result:
        result = result.set_index("datetime")
    result.index = pd.to_datetime(result.index)
    result.index.name = "datetime"
    return result


def _operation_by_datetime(
    index: pd.DatetimeIndex,
    matrix: pd.DataFrame,
) -> pd.DataFrame:
    operation = matrix.copy()
    if "month" in operation.index:
        month_labels = operation.loc["month"].astype(str)
        operation = operation.drop(index="month").transpose()
        operation.index = month_labels.to_numpy()
    operation.index = operation.index.map(str)
    month_keys = index.strftime("%Y-%m")
    if not set(month_keys).intersection(operation.index):
        operation.index = [
            f"{index[0].year + (int(month) - 1) // 12}-"
            f"{((int(month) - 1) % 12) + 1:02d}"
            for month in operation.index
        ]
    operation = operation.apply(pd.to_numeric, errors="raise")
    result = operation.reindex(month_keys).fillna(1.0)
    result.index = index
    return result.astype(float)
