from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

from source.data_structures.HP import HPUser
from source.energy.hvac.heat_pump import hp_energy_consumption
from source.energy.hvac.results import df_results_generator
from source.energy.hvac.thermal import thermal_load_calculator


@dataclass(frozen=True, slots=True)
class NonOptimizedHVACResult:
    profiles: dict[str, pd.DataFrame]
    indoor_temperatures: dict[str, np.ndarray]
    thermal_power: dict[str, np.ndarray]
    heating_power: dict[str, np.ndarray]
    cooling_power: dict[str, np.ndarray]


def simulate_non_optimized(
    hp_users: Sequence[HPUser],
    weather: pd.DataFrame,
    coordinates: list[list[object]],
    simulation_interval: str,
    *,
    heating_months: Sequence[int] = (1, 2, 3, 11, 12),
    cooling_months: Sequence[int] = (5, 6, 7, 8, 9),
    heating_hours: Sequence[int] = (0, 7, 8, 18, 19, 20, 21, 22, 23),
    cooling_hours: Sequence[int] = (0, 7, 8, 18, 19, 20, 21, 22, 23),
) -> NonOptimizedHVACResult:
    """Run the legacy 5R3C and heat-pump formulas from explicit inputs."""
    climate = weather.copy()
    climate["datetime"] = pd.to_datetime(climate["datetime"])
    months = climate["datetime"].dt.month
    hours = climate["datetime"].dt.hour
    external_temperature = climate["temp_air"].to_numpy()
    external_humidity = climate["relative_humidity"].to_numpy()
    interval_hours = pd.Timedelta(simulation_interval) / pd.Timedelta(hours=1)
    n_intervals = len(climate)

    profiles: dict[str, pd.DataFrame] = {}
    indoor_temperatures: dict[str, np.ndarray] = {}
    thermal_power: dict[str, np.ndarray] = {}
    heating_power: dict[str, np.ndarray] = {}
    cooling_power: dict[str, np.ndarray] = {}
    accumulated = pd.DataFrame()

    for hp_user in hp_users:
        thermal, indoor = thermal_load_calculator(
            hp_user,
            climate.copy(),
            n_intervals,
            months,
            hours,
            coordinates,
            external_temperature,
            list(heating_months),
            list(cooling_months),
            list(heating_hours),
            list(cooling_hours),
        )
        heating_load = thermal.copy()
        heating_load[heating_load < 0] = 0
        cooling_load = thermal.copy()
        cooling_load[cooling_load > 0] = 0
        heating = hp_energy_consumption(
            hp_user,
            heating_load,
            n_intervals,
            months,
            hours,
            external_temperature,
            indoor,
            external_humidity,
            simulation_interval,
            list(heating_months),
            list(cooling_months),
            list(heating_hours),
        )
        cooling = hp_energy_consumption(
            hp_user,
            cooling_load,
            n_intervals,
            months,
            hours,
            external_temperature,
            indoor,
            external_humidity,
            simulation_interval,
            list(heating_months),
            list(cooling_months),
            list(cooling_hours),
        )
        for user_index in range(heating.shape[1]):
            user_name = hp_user.users[user_index].name
            accumulated = df_results_generator(
                thermal[:, user_index],
                heating[:, user_index],
                cooling[:, user_index],
                float(interval_hours),
                climate,
                n_intervals,
                accumulated,
            )
            profiles[user_name] = accumulated.copy()

        indoor_temperatures[hp_user.user_name] = indoor
        thermal_power[hp_user.user_name] = thermal
        heating_power[hp_user.user_name] = heating
        cooling_power[hp_user.user_name] = cooling

    return NonOptimizedHVACResult(
        profiles=profiles,
        indoor_temperatures=indoor_temperatures,
        thermal_power=thermal_power,
        heating_power=heating_power,
        cooling_power=cooling_power,
    )


def add_hvac_consumption(
    load_profiles: pd.DataFrame,
    hvac_profiles: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Add the accepted per-user HVAC profiles to matching load columns."""
    adjusted = load_profiles.copy()
    for user_name, profile in hvac_profiles.items():
        if user_name not in adjusted:
            raise ValueError(f"HVAC user {user_name!r} is absent from load profiles")
        consumption = profile["energy consumption [kWh]"].iloc[: len(adjusted)]
        consumption.index = adjusted.index
        adjusted[user_name] = adjusted[user_name] + consumption
    return adjusted
