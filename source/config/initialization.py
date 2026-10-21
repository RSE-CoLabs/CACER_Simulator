# Architecture: Transform source configuration tables into normalized calendars, registries, matrices, and domain objects.

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

import holidays
import numpy as np
import pandas as pd

from source.data_structures import (
    Battery,
    CalendarData,
    Cacer,
    ConfigurationData,
    ConfigurationMatrices,
    DomainObjectRegistry,
    HeatPumpProperties,
    BuildingProperties,
    PV,
    Plant,
    RegistryData,
    SimulationConfig,
    User,
)


@dataclass(slots=True)
# Architecture: Carry user-table inputs and derived values through user normalization.

class UserInitialization:
    user_types: dict[str, dict[str, Any]]
    users: dict[str, dict[str, Any]]
    cacer_users: dict[str, dict[str, Any]]
    recap: dict[str, Any]


# Architecture: Create the simulation-wide time indexes consumed by all domains.

def generate_calendar(
    settings: Mapping[str, Any],
    tariff_periods: pd.DataFrame,
) -> CalendarData:
    start_date = str(settings["start_date"])
    project_lifetime_years = int(settings["project_lifetime_yrs"])
    delta_t = str(settings["delta_t"])
    end_date = f"{int(start_date[:4]) + project_lifetime_years}-01-01"

    calendar = pd.DataFrame(
        {"datetime": pd.date_range(start=start_date, end=end_date, freq=delta_t)}
    ).iloc[:-1]
    calendar["day_week"] = calendar.datetime.dt.dayofweek
    calendar["day"] = calendar.datetime.dt.day
    italian_holidays = holidays.IT()
    calendar["holiday"] = calendar["datetime"].apply(
        lambda timestamp: timestamp.date() in italian_holidays
    )

    day_groups = {
        0: ("Lav", calendar[(calendar.day_week == 0) & ~calendar.holiday]),
        1: ("Lav", calendar[(calendar.day_week == 1) & ~calendar.holiday]),
        2: ("Lav", calendar[(calendar.day_week == 2) & ~calendar.holiday]),
        3: ("Lav", calendar[(calendar.day_week == 3) & ~calendar.holiday]),
        4: ("Lav", calendar[(calendar.day_week == 4) & ~calendar.holiday]),
        5: ("Sab", calendar[(calendar.day_week == 5) & ~calendar.holiday]),
        6: ("Dom", calendar[(calendar.day_week == 6) | calendar.holiday]),
    }
    intervals_per_day = _intervals_per_day(delta_t)
    populated: list[pd.DataFrame] = []
    for tariff_column, group in day_groups.values():
        group = group.copy()
        number_of_days = int(group.shape[0] / intervals_per_day)
        values = np.tile(tariff_periods[tariff_column].to_numpy(), number_of_days)
        if len(values) != len(group):
            raise ValueError(
                f"Tariff profile {tariff_column} has {len(values)} values for "
                f"{len(group)} calendar rows"
            )
        group.insert(4, "fascia", values)
        populated.append(group)

    calendar = pd.concat(populated, sort=False).sort_index()
    calendar.drop(columns=["day"], inplace=True)
    calendar["day_flag"] = "Working_day"
    calendar.loc[calendar["day_week"] == 5, "day_flag"] = "Saturday"
    calendar.loc[calendar["day_week"] == 6, "day_flag"] = "Sunday"
    calendar.loc[calendar["holiday"], "day_flag"] = "Sunday"

    months = calendar.datetime.dt.strftime("%Y-%m").unique()
    monthly_calendar = pd.DataFrame(
        {
            "month_number": np.arange(1, len(months) + 1, dtype=int),
            "month": months,
        }
    )
    return CalendarData(
        calendar=calendar.reset_index(drop=True),
        monthly_calendar=monthly_calendar,
    )


# Architecture: Expand configured user rows into normalized user registries and participation metadata.

def initialize_users(
    settings: Mapping[str, Any],
    user_rows: pd.DataFrame,
    *,
    base: int = 36,
) -> UserInitialization:
    users_frame = user_rows[user_rows["flag"] == True].copy()  # noqa: E712
    for column in users_frame.select_dtypes(include=["object"]).columns:
        users_frame[column] = users_frame[column].where(
            users_frame[column].notna(),
            None,
        )
    for column in (
        "flag",
        "consuming",
        "producing",
        "flag_DSM",
        "new_plant",
        "mv_cabinet",
        "heat_load",
        "flag_cacer",
        "dummy_user",
        "condominium",
    ):
        users_frame[column] = users_frame[column].fillna(False).astype(bool)
    users_frame["grant_pnrr"] = users_frame["grant_pnrr"].fillna(0)
    _validate_user_rows(users_frame)

    users_frame.set_index("user_type", inplace=True)
    users_frame.drop(columns=["number_type_id"], inplace=True)
    for column in ("num", "pv", "battery", "wind"):
        users_frame[column] = users_frame[column].fillna(0).astype(int)
    users_frame["dummy_user"] = users_frame["dummy_user"].fillna(False).astype(bool)

    users: dict[str, dict[str, Any]] = {}
    cacer_users: dict[str, dict[str, Any]] = {}
    users_count = 1
    for user_type in users_frame.index:
        for _ in range(int(users_frame.loc[user_type, "num"])):
            encoded = np.base_repr(users_count, base=base, padding=3)[-3:]
            category_id = settings["category_id"][
                users_frame.loc[user_type, "category"]
            ]
            if users_frame.loc[user_type, "type"] == "consumer":
                category_id = category_id.lower()
            user_id = f"u_{category_id}{encoded}"
            values = users_frame.loc[user_type].to_dict()
            values["user_type"] = user_type
            users[user_id] = values
            if bool(users_frame.loc[user_type, "flag_cacer"]):
                cacer_users[user_id] = deepcopy(values)
            users_count += 1
    if users_count >= base**3:
        raise ValueError("The number of users exceeds the three-digit ID capacity")

    seniority = (
        pd.DataFrame.from_dict(users, orient="index")
        .sort_values(["entry_month"], ascending=True)
        .index
    )
    for level, user_id in enumerate(seniority, start=1):
        users[user_id]["seniority_level"] = level
        if user_id in cacer_users:
            cacer_users[user_id]["seniority_level"] = level

    user_types = {
        str(user_type): users_frame.loc[user_type].to_dict()
        for user_type in users_frame.index
    }
    recap = _build_user_recap(
        settings,
        user_types,
        users,
        cacer_users,
        list(seniority),
    )
    return UserInitialization(user_types, users, cacer_users, recap)


# Architecture: Normalize plant rows into generating-asset registries and lifecycle data.

def initialize_plants(
    users: Mapping[str, Mapping[str, Any]],
    recap: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    plants: dict[str, dict[str, Any]] = {}
    for user_id in [*recap["list_prosumers"], *recap["list_producers"]]:
        plant_id = user_id.replace("u_", "p_")
        plant = deepcopy(dict(users[user_id]))
        plant["titolare_POD"] = user_id
        plant["installed_capacity"] = plant["pv"] + plant["wind"]
        for key in ("grant_pnrr", "grant_private", "debt"):
            if pd.isna(plant[key]):
                plant[key] = 0
        if pd.isna(plant["disbursement_month"]) or plant["disbursement_month"] == 0:
            raise ValueError(
                f"Invalid disbursement_month for {plant['user_type']}: "
                f"{plant['disbursement_month']}"
            )
        plants[plant_id] = plant

    ordered_plants = (
        pd.DataFrame.from_dict(plants, orient="index")
        .sort_values(
            ["commissioning_month", "installed_capacity"],
            ascending=[True, True],
        )
        .index
        .tolist()
        if plants
        else []
    )
    for level, plant_id in enumerate(ordered_plants, start=1):
        plants[plant_id]["seniority_level"] = level
    recap["plants_sorted_by_seniority"] = ordered_plants
    return plants


# Architecture: Build the time-varying user membership matrix used by ownership and energy allocation.

def membership_matrix(
    monthly_calendar: pd.DataFrame,
    users: Mapping[str, Mapping[str, Any]],
    recap: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    membership = monthly_calendar.set_index("month_number").copy()
    entries = monthly_calendar.set_index("month_number").copy()
    # Legacy YAML persistence sorted registry keys before this matrix was built.
    for user_id in sorted(users):
        user = users[user_id]
        entry_month = int(user["entry_month"])
        exit_month = _exit_month(user["exit_month"], membership.index[-1])
        entries[user_id] = 0
        entries.loc[entry_month, user_id] = 1
        membership[user_id] = [
            int(entry_month <= month < exit_month) for month in membership.index
        ]
    membership = membership.T
    entries = entries.T
    recap["users_present_month_1"] = list(
        membership[membership[1] == 1].index
    )
    return membership, entries


# Architecture: Build plant availability and operation matrices over the simulation horizon.

def plant_operation_matrices(
    monthly_calendar: pd.DataFrame,
    user_types: Mapping[str, Mapping[str, Any]],
    plants: Mapping[str, Mapping[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    plant_types = monthly_calendar.set_index("month_number").copy()
    for user_type, values in user_types.items():
        if not values["producing"]:
            continue
        commissioning = int(values["commissioning_month"])
        exit_month = _exit_month(values["exit_month"], plant_types.index[-1])
        plant_types[user_type] = [
            int(commissioning <= month < exit_month) for month in plant_types.index
        ]

    plant_operations = monthly_calendar.set_index("month_number").copy()
    for plant_id, values in plants.items():
        commissioning = int(values["commissioning_month"])
        exit_month = _exit_month(values["exit_month"], plant_operations.index[-1])
        plant_operations[plant_id] = [
            int(commissioning <= month < exit_month)
            for month in plant_operations.index
        ]
    return plant_types.T, plant_operations.T


# Architecture: Assemble the complete normalized configuration contract for the simulator.

def initialize_configuration(
    settings: Mapping[str, Any],
    tariff_periods: pd.DataFrame,
    user_rows: pd.DataFrame,
    building_properties: Mapping[str, BuildingProperties],
    heat_pump_properties: Mapping[str, HeatPumpProperties],
) -> ConfigurationData:
    calendars = generate_calendar(settings, tariff_periods)
    initialized_users = initialize_users(settings, user_rows)
    plants = initialize_plants(initialized_users.users, initialized_users.recap)
    membership, entries = membership_matrix(
        calendars.monthly_calendar,
        initialized_users.users,
        initialized_users.recap,
    )
    plant_types, plant_operations = plant_operation_matrices(
        calendars.monthly_calendar,
        initialized_users.user_types,
        plants,
    )
    domain_objects = _build_domain_objects(
        settings,
        initialized_users.user_types,
        initialized_users.users,
        plants,
        building_properties,
        heat_pump_properties,
    )
    return ConfigurationData(
        settings=settings,
        calendars=calendars,
        registries=RegistryData(
            user_types=initialized_users.user_types,
            users=initialized_users.users,
            cacer_users=initialized_users.cacer_users,
            plants=plants,
        ),
        matrices=ConfigurationMatrices(
            membership=membership,
            user_entry=entries,
            plant_type_operation=plant_types,
            plant_operation=plant_operations,
        ),
        domain_objects=domain_objects,
        recap=initialized_users.recap,
    )


# Architecture: Derive CACER scenario membership and configuration groupings from normalized users and plants.

def setting_CACER_scenario(
    recap: dict[str, Any],
    case_denomination: str,
    cacer_type: str,
    repartition_scheme: str,
) -> None:
    recap["case_denomination"] = case_denomination
    recap["type_of_cacer"] = cacer_type
    recap["incentives_repartition_scheme"] = repartition_scheme


# Architecture: Apply configuration edits to user rows before registry construction.

def edit_user_rows(
    user_rows: pd.DataFrame,
    variable: str,
    user_type: str,
    value: Any,
) -> pd.DataFrame:
    if variable not in user_rows:
        raise KeyError(f"Unknown user field: {variable}")
    matches = user_rows["user_type"] == user_type
    if not matches.any():
        raise KeyError(f"Unknown user type: {user_type}")
    updated = user_rows.copy()
    updated.loc[matches, variable] = value
    return updated


# Architecture: Reset generated user-count fields while preserving source row structure.

def clear_user_counts(user_rows: pd.DataFrame) -> pd.DataFrame:
    if "num" not in user_rows:
        raise KeyError("Missing user field: num")
    updated = user_rows.copy()
    updated["num"] = np.nan
    return updated


# Architecture: Select and normalize a configured allocation scheme.

def set_repartition_scheme(
    scenario: Mapping[str, Any],
    scheme: str,
    value: Any,
) -> dict[str, Any]:
    key = f"{scheme}_repartition_scheme"
    if key not in {
        "incentives_repartition_scheme",
        "opex_repartition_scheme",
        "surplus_repartition_scheme",
    }:
        raise ValueError(f"Unknown repartition scheme: {scheme}")
    updated = dict(scenario)
    updated[key] = value
    return updated


# Architecture: Merge externally supplied user definitions into the configuration input table.

def merge_external_user_rows(
    user_rows: pd.DataFrame,
    load_rows: pd.DataFrame,
) -> pd.DataFrame:
    if "flag" not in load_rows:
        raise KeyError("Missing load field: flag")
    first_field = load_rows.columns.get_loc("flag")
    imported = load_rows.iloc[:, first_field:].copy()
    imported.rename(columns={"Location": "location"}, inplace=True)
    target_columns = list(user_rows.columns[1:])
    for column in target_columns:
        if column not in imported:
            imported[column] = False if column == "error" else 0
    imported = imported.reindex(columns=target_columns)
    imported.insert(0, user_rows.columns[0], np.nan)
    return pd.concat([user_rows, imported], ignore_index=True)


# Architecture: Construct typed PV, battery, building, HVAC, plant, and user objects.

def _build_domain_objects(
    settings: Mapping[str, Any],
    user_types: Mapping[str, Mapping[str, Any]],
    users: Mapping[str, Mapping[str, Any]],
    plants: Mapping[str, Mapping[str, Any]],
    building_properties: Mapping[str, BuildingProperties],
    heat_pump_properties: Mapping[str, HeatPumpProperties],
) -> DomainObjectRegistry:
    simulation = SimulationConfig.from_mapping(settings)
    normalized_users = {
        user_id: User.from_registry(user_id, values)
        for user_id, values in users.items()
    }
    normalized_plants = {
        plant_id: Plant.from_registry(plant_id, values)
        for plant_id, values in plants.items()
    }
    photovoltaic = {
        plant_id: PV(
            plant_id=plant_id,
            capacity_kwp=float(values["pv"]),
            tilt_degrees=float(values["tilt_angle"]),
            azimuth_degrees=float(values["azimuth"]),
            mounting=values["pv_mounting"],
            derating_factor=float(settings["pv_derating_factor"]),
        )
        for plant_id, values in plants.items()
        if float(values["pv"]) > 0
    }
    batteries = {
        user_id: Battery(
            owner_id=user_id,
            capacity_kwh=float(values["battery"]),
            depth_of_discharge=float(settings["dod"]),
            round_trip_efficiency=float(settings["round_trip_efficiency"]),
            derating_factor_per_cycle=float(settings["battery_derating_factor"]),
        )
        for user_id, values in users.items()
        if float(values["battery"]) > 0
    }
    return DomainObjectRegistry(
        simulation=simulation,
        cacer=Cacer.from_values(
            simulation.cacer_type,
            simulation.index_frequency,
            user_types,
        ),
        users=normalized_users,
        plants=normalized_plants,
        photovoltaic=photovoltaic,
        batteries=batteries,
        building_properties=dict(building_properties),
        heat_pump_properties=dict(heat_pump_properties),
    )


# Architecture: Translate the configured timestep into the common daily interval count.

def _intervals_per_day(delta_t: str) -> int:
    interval = pd.Timedelta(delta_t)
    intervals = pd.Timedelta(days=1) / interval
    if not float(intervals).is_integer():
        raise ValueError(f"delta_t must divide one day exactly: {delta_t}")
    return int(intervals)


# Architecture: Check normalized user rows before they enter registries and matrices.

def _validate_user_rows(users: pd.DataFrame) -> None:
    if users["user_type"].duplicated().any():
        raise ValueError("Active user_type identifiers must be unique")
    if users["denomination"].duplicated().any():
        raise ValueError("Active user type denominations must be unique")
    too_long = users.loc[users["user_type"].astype(str).str.len() > 31, "user_type"]
    if not too_long.empty:
        raise ValueError(
            f"User type names exceed the Excel 31-character limit: {too_long.tolist()}"
        )


# Architecture: Create recap metadata that summarizes active user and CACER composition.

def _build_user_recap(
    settings: Mapping[str, Any],
    user_types: Mapping[str, Mapping[str, Any]],
    users: Mapping[str, Mapping[str, Any]],
    cacer_users: Mapping[str, Mapping[str, Any]],
    seniority: list[str],
) -> dict[str, Any]:
    recap: dict[str, Any] = {
        "users_sorted_on_seniority": seniority,
        "type_of_cacer": settings["type_of_cacer"],
    }
    for user_kind in ("prosumer", "producer", "consumer"):
        plural = f"{user_kind}s"
        recap[f"numero_{plural}"] = sum(
            values["num"]
            for values in user_types.values()
            if values["type"] == user_kind
        )
        recap[f"list_{plural}"] = [
            user_id for user_id, values in users.items() if values["type"] == user_kind
        ]
        recap[f"list_{plural}_CACER"] = [
            user_id
            for user_id, values in cacer_users.items()
            if values["type"] == user_kind
        ]
        recap[f"list_types_{plural}"] = _ordered_unique(
            values["user_type"]
            for values in users.values()
            if values["type"] == user_kind
        )
        recap[f"list_types_{plural}_CACER"] = _ordered_unique(
            values["user_type"]
            for values in cacer_users.values()
            if values["type"] == user_kind
        )

    pv_capacities: list[int] = []
    battery_capacities: list[int] = []
    for values in user_types.values():
        if values["type"] == "consumer":
            continue
        for _ in range(int(values["num"])):
            if not pd.isna(values["pv"]):
                pv_capacities.append(int(values["pv"]))
            if not pd.isna(values["battery"]):
                battery_capacities.append(int(values["battery"]))

    recap.update(
        {
            "dummy_users": [
                user_type
                for user_type, values in user_types.items()
                if values["dummy_user"]
            ],
            "all_PV": pv_capacities,
            "all_storage": battery_capacities,
            "list_user_types": _ordered_unique(
                values["user_type"] for values in users.values()
            ),
            "all_users": list(users),
            "list_user_types_CACER": _ordered_unique(
                values["user_type"] for values in cacer_users.values()
            ),
            "all_users_CACER": list(cacer_users),
            "configurations": _ordered_unique(
                values["CP"] for values in cacer_users.values()
            ),
            "stakeholders": _ordered_unique(
                values["stakeholder"]
                for values in cacer_users.values()
                if not pd.isnull(values["stakeholder"])
            ),
            "PV_tot": sum(pv_capacities),
            "batt_tot": sum(battery_capacities),
            "total_CACER_members": len(cacer_users),
            "total_non_dummy_CACER_members": sum(
                not values["dummy_user"] for values in cacer_users.values()
            ),
            "PV_max": max(pv_capacities, default=0),
            "PV_min": min(pv_capacities, default=0),
            "batt_max": max(battery_capacities, default=0),
            "batt_min": min(battery_capacities, default=0),
            "total_CACER_users": len(cacer_users),
            "total_grid_users": len(users),
        }
    )
    return recap


# Architecture: Preserve input order while removing duplicate configuration values.

def _ordered_unique(values: Any) -> list[Any]:
    return list(dict.fromkeys(values))


# Architecture: Normalize user exit timing against the configured simulation horizon.

def _exit_month(value: Any, final_month: int) -> int:
    return final_month + 1 if value == "end" else int(value)
