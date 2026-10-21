from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import pandas as pd

from source.data_structures import (
    ConfigResults,
    EnergyResults,
    HPUser,
    LoadResults,
)
from source.energy.hvac.heat_pump import (
    Psat_calculator,
    ah_ratio_calculator,
    defrost_op,
    hp_efficiency,
    hp_energy_consumption,
    hp_operating_curve,
    hp_performances_autonomous,
    hp_performances_centralized,
    hp_power_curve_max,
    wet_bulb_temperature,
)
from source.energy.hvac.non_optimized import (
    add_hvac_consumption,
    simulate_non_optimized,
)
from source.energy.hvac.optimized import simulate_optimized
from source.energy.hvac.solar import get_irradiance, solar_thermal_contribution
from source.energy.hvac.thermal import (
    model_th_fluxes,
    th_fluxes_generator,
    thermal_load_calculator,
)


@dataclass(frozen=True, slots=True)
class HVACOptions:
    """Explicit inputs and operating choices for native HVAC simulation."""

    weather: pd.DataFrame
    coordinates: tuple[float, float, str, float, str]
    building_archetypes: Mapping[str, Sequence[str]] = field(default_factory=dict)
    pv_production: pd.DataFrame | None = None
    optimization_month: str = "Gen"
    optimization_year: int = 2005
    optimization_days: int | None = None
    solver_messages: bool = False
    relative_gap: float = 0.005
    heating_months: tuple[int, ...] = (1, 2, 3, 11, 12)
    cooling_months: tuple[int, ...] = (5, 6, 7, 8, 9)
    heating_hours: tuple[int, ...] = (0, 7, 8, 18, 19, 20, 21, 22, 23)
    cooling_hours: tuple[int, ...] = (0, 7, 8, 18, 19, 20, 21, 22, 23)


@dataclass(frozen=True, slots=True)
class HPBoundaryInput:
    """All values needed by HVAC; domain calculations perform no file reads."""

    config: ConfigResults
    load: LoadResults | None = None
    external_profile: Any | None = None
    options: HVACOptions | None = None


def run_hp_operation(
    boundary: HPBoundaryInput,
    *,
    mode: str = "disabled",
) -> EnergyResults:
    normalized = mode.strip().lower().replace("-", "_")
    if normalized in {"disabled", "off", "none"}:
        return EnergyResults(
            hvac={},
            metadata={"domain": "hvac", "mode": "disabled", "status": "disabled"},
        )
    if normalized in {"external", "external_profile", "profile"}:
        if boundary.external_profile is None:
            raise ValueError("external HVAC mode requires boundary.external_profile")
        return EnergyResults(
            hvac={"load_profiles": boundary.external_profile},
            metadata={"domain": "hvac", "mode": "external", "status": "completed"},
        )
    if normalized == "non_optimized":
        return _run_non_optimized(boundary)
    if normalized == "optimized":
        return _run_optimized(boundary)
    raise ValueError(
        "mode must be optimized, non_optimized, external, or disabled"
    )


def _run_non_optimized(boundary: HPBoundaryInput) -> EnergyResults:
    if boundary.options is None:
        raise ValueError("non_optimized HVAC requires explicit HVACOptions")
    if boundary.load is None:
        raise ValueError("non_optimized HVAC requires LoadResults")
    profiles = boundary.load.profiles.get("load")
    if not isinstance(profiles, pd.DataFrame):
        raise ValueError("LoadResults.profiles['load'] must be a DataFrame")

    hp_users = _build_hp_users(boundary.config, boundary.options, "non_optimized")
    result = simulate_non_optimized(
        hp_users,
        boundary.options.weather,
        [list(boundary.options.coordinates)],
        boundary.config.normalized.domain_objects.simulation.index_frequency,
        heating_months=boundary.options.heating_months,
        cooling_months=boundary.options.cooling_months,
        heating_hours=boundary.options.heating_hours,
        cooling_hours=boundary.options.cooling_hours,
    )
    adjusted = add_hvac_consumption(profiles, result.profiles)
    return EnergyResults(
        hvac={
            "profiles": result.profiles,
            "load_profiles": adjusted,
            "indoor_temperatures": result.indoor_temperatures,
            "thermal_power": result.thermal_power,
            "heating_power": result.heating_power,
            "cooling_power": result.cooling_power,
        },
        metadata={
            "domain": "hvac",
            "mode": "non_optimized",
            "status": "completed",
        },
    )


def _run_optimized(boundary: HPBoundaryInput) -> EnergyResults:
    if boundary.options is None:
        raise ValueError("optimized HVAC requires explicit HVACOptions")
    if boundary.options.pv_production is None:
        raise ValueError("optimized HVAC requires explicit PV production")
    if boundary.config.normalized is None:
        raise ValueError("optimized HVAC requires normalized configuration")
    hp_users = _build_hp_users(boundary.config, boundary.options, "optimized")
    objects = boundary.config.normalized.domain_objects
    result = simulate_optimized(
        objects.cacer.cacer_type,
        objects.simulation.index_frequency,
        hp_users,
        boundary.options.weather,
        [list(boundary.options.coordinates)],
        boundary.options.pv_production,
        boundary.options.optimization_month,
        boundary.options.optimization_year,
        days=boundary.options.optimization_days,
        solver_messages=boundary.options.solver_messages,
        relative_gap=boundary.options.relative_gap,
    )
    hvac: dict[str, Any] = {
        "profiles": {"optimized": result.profile},
        "optimization_objectives": result.objective_values,
        "solver_statuses": result.solver_statuses,
        "decisions": result.decisions,
    }
    if boundary.load is not None:
        profiles = boundary.load.profiles.get("load")
        if isinstance(profiles, pd.DataFrame):
            adjusted = profiles.copy()
            interval_hours = (
                pd.Timedelta(objects.simulation.index_frequency)
                / pd.Timedelta(hours=1)
            )
            for user_index, hp_user in enumerate(hp_users):
                if hp_user.user_name in adjusted:
                    count = len(result.decisions["energy"])
                    addition = (
                        result.decisions["energy"][:, user_index]
                        * float(interval_hours)
                        / 1000
                    )
                    adjusted.iloc[:count, adjusted.columns.get_loc(hp_user.user_name)] += addition
            hvac["load_profiles"] = adjusted
    return EnergyResults(
        hvac=hvac,
        metadata={
            "domain": "hvac",
            "mode": "optimized",
            "status": "completed",
        },
    )


def _build_hp_users(
    config_results: ConfigResults,
    options: HVACOptions,
    mode: str,
) -> tuple[HPUser, ...]:
    normalized = config_results.normalized
    if normalized is None:
        raise ValueError("HVAC requires normalized configuration")
    objects = normalized.domain_objects
    hp_users: list[HPUser] = []
    active_types = [
        (name, values)
        for name, values in normalized.registries.user_types.items()
        if bool(values["heat_load"]) and not bool(values["condominium"])
    ]
    for ordinal, (name, values) in enumerate(active_types):
        archetypes = tuple(
            options.building_archetypes.get(
                name,
                _default_archetypes(name, values, ordinal, mode),
            )
        )
        expected = 1 if values["hvac_type"] == "autonomous" else int(values["num"])
        if len(archetypes) != expected:
            raise ValueError(
                f"HVAC user {name!r} requires {expected} building archetypes, "
                f"received {len(archetypes)}"
            )
        try:
            buildings = [
                objects.building_properties[archetype]
                for archetype in archetypes
            ]
        except KeyError as exc:
            raise ValueError(f"Unknown building archetype {exc.args[0]!r}") from exc
        hp_key = (
            "heat_pump_autonomous"
            if values["hvac_type"] == "autonomous"
            else "heat_pump_centralized"
        )
        hp_users.append(
            HPUser.from_values(
                name,
                values,
                buildings,
                objects.heat_pump_properties[hp_key],
                objects.simulation.index_frequency,
            )
        )
    return tuple(hp_users)


def _default_archetypes(
    user_name: str,
    values: Mapping[str, Any],
    ordinal: int,
    mode: str,
) -> tuple[str, ...]:
    if values["hvac_type"] == "autonomous":
        accepted = (
            {
                "household_small_1": "building_west",
                "household_small_prosumer": "building_roof_west",
            }
            if mode == "optimized"
            else {
                "household_small_1": "building_roof_east",
                "household_small_prosumer": "building_east",
            }
        )
        return (accepted.get(user_name, ("building_roof_east", "building_east")[ordinal % 2]),)
    legacy_order = (
        "building_floor_east",
        "building_floor_west",
        "building_west",
        "building_roof_east",
        "building_roof_west",
    )
    count = int(values["num"])
    return tuple(legacy_order[index % len(legacy_order)] for index in range(count))


def run_disabled(boundary: HPBoundaryInput) -> EnergyResults:
    return run_hp_operation(boundary, mode="disabled")


def run_external_profile(
    boundary: HPBoundaryInput,
    profile: Any,
) -> EnergyResults:
    return run_hp_operation(
        HPBoundaryInput(boundary.config, boundary.load, profile, boundary.options),
        mode="external",
    )


def run_non_optimized(boundary: HPBoundaryInput) -> EnergyResults:
    return run_hp_operation(boundary, mode="non_optimized")


def run_optimized(boundary: HPBoundaryInput) -> EnergyResults:
    return run_hp_operation(boundary, mode="optimized")


adding_HVAC_energy_consumption = add_hvac_consumption
non_optimized = run_non_optimized
