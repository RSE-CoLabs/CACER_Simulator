from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from source.data_structures import (
    ConfigResults,
    EnergyResults,
    LoadResults,
    PipelineOptions,
    RunContext,
)
from source.energy.CACER_flows import CACER_energy_flows
from source.energy.CACER_flows_for_incentives import CACER_shared_energy
from source.energy.HP_operation import HVACOptions, HPBoundaryInput, run_hp_operation
from source.energy.PV_generation import (
    PVSimulationOptions,
    simulate_pv_profiles,
    validate_external_pv_profiles,
)


HP_MODES = {"optimized", "non_optimized", "external", "disabled"}
PV_MODES = {"simulated", "external", "disabled"}
FLOW_VERSIONS = {"legacy"}


def run_energy_pipeline(
    run_context: RunContext,
    config_results: ConfigResults,
    upstream_results: Any | None = None,
    options: PipelineOptions | None = None,
) -> EnergyResults:
    """Run the energy domain entirely in memory, then persist its outputs."""
    selected_options = options or run_context.options.energy
    if not selected_options.enabled:
        return EnergyResults(
            metadata={
                "domain": "energy",
                "enabled": False,
                "version": selected_options.version,
                "status": "disabled",
            }
        )
    if not isinstance(upstream_results, LoadResults):
        raise TypeError("Energy pipeline requires upstream LoadResults")
    if config_results.normalized is None:
        raise ValueError("Energy pipeline requires normalized configuration results")

    settings = selected_options.settings
    hp_mode = _mode(settings, "hp_mode", "disabled", HP_MODES)
    pv_mode = _mode(settings, "pv_mode", "simulated", PV_MODES)
    flow_version = selected_options.version or str(
        settings.get("flow_version", "legacy")
    )
    if flow_version not in FLOW_VERSIONS:
        raise ValueError(
            f"Unsupported energy flow version {flow_version!r}; "
            f"expected one of {sorted(FLOW_VERSIONS)}"
        )

    load_profiles = _load_profiles(upstream_results)
    production = _run_pv(pv_mode, config_results, settings)
    hp_results = _run_hp(
        hp_mode,
        config_results,
        upstream_results,
        settings,
        production,
    )
    energy_load = _load_with_hvac(load_profiles, hp_results)

    normalized = config_results.normalized
    config = config_results.configuration
    user_flows = CACER_energy_flows(
        energy_load,
        production,
        normalized.registries.user_types,
        normalized.matrices.plant_type_operation,
        dod=float(config["dod"]),
        round_trip_efficiency=float(config["round_trip_efficiency"]),
        battery_derating_factor=float(config["battery_derating_factor"]),
        battery_enabled=bool(settings.get("battery_enabled", True)),
    )
    shared = CACER_shared_energy(
        user_flows,
        normalized.registries.user_types,
        normalized.registries.plants,
        normalized.recap,
    )
    artifacts = _save_energy_outputs(
        run_context.energy_output,
        production,
        hp_results,
        user_flows,
        shared.aggregate_hourly,
        shared.incentive_hourly,
        shared.incentive_yearly,
        shared.valorization_hourly,
    )
    return EnergyResults(
        flows={
            "users": user_flows,
            "aggregate_hourly": shared.aggregate_hourly,
        },
        production={"pv": production},
        hvac=hp_results.hvac,
        incentives={
            "hourly": shared.incentive_hourly,
            "yearly": shared.incentive_yearly,
            "valorization_hourly": shared.valorization_hourly,
        },
        artifacts=artifacts,
        metadata={
            "domain": "energy",
            "enabled": True,
            "version": flow_version,
            "status": "completed",
            "hp_mode": hp_mode,
            "pv_mode": pv_mode,
            "battery_enabled": bool(settings.get("battery_enabled", True)),
            "pv_simulation": production.attrs.get("pv_simulation"),
        },
    )


def _mode(
    settings: Mapping[str, Any],
    key: str,
    default: str,
    allowed: set[str],
) -> str:
    value = str(settings.get(key, default)).strip().lower().replace("-", "_")
    if value not in allowed:
        raise ValueError(f"{key} must be one of {sorted(allowed)}")
    return value


def _load_profiles(load_results: LoadResults) -> pd.DataFrame:
    profiles = load_results.profiles.get("load")
    if not isinstance(profiles, pd.DataFrame):
        raise ValueError("LoadResults.profiles['load'] must be a pandas DataFrame")
    return profiles.copy()


def _run_hp(
    mode: str,
    config_results: ConfigResults,
    load_results: LoadResults,
    settings: Mapping[str, Any],
    production: pd.DataFrame,
) -> EnergyResults:
    external = settings.get("external_hvac_profile")
    hp_options = None
    if mode in {"non_optimized", "optimized"}:
        hp_options = _hp_options(config_results, settings, production)
    return run_hp_operation(
        HPBoundaryInput(config_results, load_results, external, hp_options),
        mode=mode,
    )


def _hp_options(
    config_results: ConfigResults,
    settings: Mapping[str, Any],
    production: pd.DataFrame,
) -> HVACOptions:
    configured = settings.get("hp_options")
    if isinstance(configured, HVACOptions):
        return configured
    values = dict(configured or {})
    if not isinstance(configured, (Mapping, type(None))):
        raise TypeError("hp_options must be HVACOptions or a mapping")
    weather = values.pop("weather", None)
    if weather is None:
        weather_path = Path(
            config_results.configuration["filename_weather_data_selected_years"]
        )
        weather = pd.read_csv(weather_path)
    if not isinstance(weather, pd.DataFrame):
        raise TypeError("hp_options.weather must be a DataFrame")
    coordinates = values.pop(
        "coordinates",
        (45.4641943, 9.1896346, "Milano", 110.0, "Etc/GMT+2"),
    )
    values.setdefault("pv_production", production)
    return HVACOptions(weather=weather, coordinates=tuple(coordinates), **values)


def _load_with_hvac(
    load_profiles: pd.DataFrame,
    hp_results: EnergyResults,
) -> pd.DataFrame:
    adjusted = hp_results.hvac.get("load_profiles")
    if adjusted is None:
        return load_profiles
    if not isinstance(adjusted, pd.DataFrame):
        raise TypeError("HVAC load_profiles result must be a pandas DataFrame")
    if not adjusted.index.equals(load_profiles.index):
        raise ValueError("HVAC-adjusted load index must match LoadResults")
    return adjusted


def _run_pv(
    mode: str,
    config_results: ConfigResults,
    settings: Mapping[str, Any],
) -> pd.DataFrame:
    calendar_frame = config_results.calendars["calendar"]
    if mode == "disabled":
        index = pd.DatetimeIndex(pd.to_datetime(calendar_frame["datetime"]))
        return pd.DataFrame(index=index)
    if mode == "external":
        external = settings.get("external_pv_profiles")
        if not isinstance(external, pd.DataFrame):
            raise ValueError(
                "external PV mode requires external_pv_profiles DataFrame"
            )
        return validate_external_pv_profiles(external, calendar_frame)
    municipalities = config_results.data_structures.get("municipalities")
    if not isinstance(municipalities, pd.DataFrame):
        raise ValueError("PV simulation requires the municipalities table")
    return simulate_pv_profiles(
        config_results.registries["user_types"],
        config_results.registries["plants"],
        calendar_frame,
        config_results.configuration,
        municipalities,
        options=_pv_options(settings),
    )


def _pv_options(settings: Mapping[str, Any]) -> PVSimulationOptions:
    configured = settings.get("pv_options")
    if configured is None:
        return PVSimulationOptions()
    if isinstance(configured, PVSimulationOptions):
        return configured
    if isinstance(configured, Mapping):
        return PVSimulationOptions(**configured)
    raise TypeError("pv_options must be PVSimulationOptions or a mapping")


def _save_energy_outputs(
    output_path: Path,
    production: pd.DataFrame,
    hp_results: EnergyResults,
    user_flows: Mapping[str, pd.DataFrame],
    aggregate: pd.DataFrame,
    incentive_hourly: pd.DataFrame,
    incentive_yearly: pd.DataFrame,
    valorization: pd.DataFrame,
) -> tuple[Path, ...]:
    artifacts: list[Path] = []
    users_path = output_path / "users"
    hvac_path = output_path / "hvac"
    users_path.mkdir(exist_ok=True)
    hvac_path.mkdir(exist_ok=True)
    artifacts.append(_save_csv(production, output_path / "pv_generation.csv"))
    artifacts.append(_save_csv(aggregate, output_path / "CACER_energy_hourly.csv"))
    artifacts.append(
        _save_csv(
            incentive_hourly,
            output_path / "shared_energy_incentive_hourly.csv",
        )
    )
    artifacts.append(
        _save_csv(
            incentive_yearly,
            output_path / "shared_energy_incentive_yearly.csv",
        )
    )
    artifacts.append(
        _save_csv(
            valorization,
            output_path / "shared_energy_valorization_hourly.csv",
        )
    )
    for user_id, frame in user_flows.items():
        artifacts.append(_save_csv(frame, users_path / f"{user_id}.csv"))
    _save_hvac_frames(hp_results.hvac, hvac_path, artifacts)
    return tuple(artifacts)


def _save_hvac_frames(
    values: Mapping[str, Any],
    output_path: Path,
    artifacts: list[Path],
    prefix: str = "",
) -> None:
    for name, value in values.items():
        artifact_name = f"{prefix}_{name}" if prefix else name
        if isinstance(value, pd.DataFrame):
            artifacts.append(_save_csv(value, output_path / f"{artifact_name}.csv"))
        elif isinstance(value, Mapping):
            _save_hvac_frames(value, output_path, artifacts, artifact_name)


def _save_csv(frame: pd.DataFrame, path: Path) -> Path:
    frame.to_csv(path)
    return path
