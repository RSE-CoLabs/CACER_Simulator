# Architecture: Coordinate raw configuration loading, normalization, and snapshot outputs.

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yaml

from source.config.initialization import initialize_configuration
from source.config.utilities import load_yaml, resolve_path
from source.data_structures import (
    BuildingProperties,
    ConfigResults,
    HeatPumpProperties,
    PipelineOptions,
    RunContext,
)


# Architecture: Load and normalize configuration inputs, then package the stage result.

def run_config_pipeline(
    run_context: RunContext,
    config_results: ConfigResults | None = None,
    upstream_results: Any | None = None,
    options: PipelineOptions | None = None,
) -> ConfigResults:
    selected_options = options or run_context.options.config
    if not selected_options.enabled:
        results = config_results or ConfigResults()
        results.metadata.update(
            {
                "domain": "config",
                "enabled": False,
                "version": selected_options.version,
                "status": "disabled",
            }
        )
        return results

    config_path = _config_path(run_context, selected_options.settings)
    settings = load_yaml(config_path)
    _validate_settings(settings, config_path)

    user_workbook = resolve_path(
        run_context.repository_root,
        settings["filename_users_CACER_xls"],
    )
    tariff_periods_path = resolve_path(
        run_context.repository_root,
        settings["filename_giorni_tipo"],
    )
    municipalities_path = resolve_path(
        run_context.repository_root,
        settings["filename_comuni_italiani"],
    )
    building_properties_path = resolve_path(
        run_context.repository_root,
        settings["building_properties_folder"],
    )
    heat_pump_properties_path = resolve_path(
        run_context.repository_root,
        settings["hp_properties_folder"],
    )
    user_rows = pd.read_excel(user_workbook, sheet_name="Utenti")
    tariff_periods = pd.read_csv(tariff_periods_path)
    municipalities = pd.read_csv(municipalities_path, encoding="unicode_escape")
    building_properties = _load_property_catalog(
        building_properties_path,
        BuildingProperties,
    )
    heat_pump_properties = _load_property_catalog(
        heat_pump_properties_path,
        HeatPumpProperties,
    )

    normalized = initialize_configuration(
        settings,
        tariff_periods,
        user_rows,
        building_properties,
        heat_pump_properties,
    )
    artifacts = _save_configuration_snapshot(run_context.config_output, normalized)
    results = config_results or ConfigResults()
    results.configuration = settings
    results.calendars = {
        "calendar": normalized.calendars.calendar,
        "monthly_calendar": normalized.calendars.monthly_calendar,
    }
    results.registries = {
        "user_types": normalized.registries.user_types,
        "users": normalized.registries.users,
        "cacer_users": normalized.registries.cacer_users,
        "plants": normalized.registries.plants,
        "recap": normalized.recap,
    }
    results.data_structures = {
        "municipalities": municipalities,
        "membership_matrix": normalized.matrices.membership,
        "user_entry_matrix": normalized.matrices.user_entry,
        "plant_type_operation_matrix": normalized.matrices.plant_type_operation,
        "plant_operation_matrix": normalized.matrices.plant_operation,
        "domain_objects": normalized.domain_objects,
    }
    results.normalized = normalized
    results.artifacts = artifacts
    results.metadata.update(
        {
            "domain": "config",
            "enabled": True,
            "version": selected_options.version,
            "status": "completed",
            "config_path": str(config_path),
            "user_workbook": str(user_workbook),
            "tariff_periods_path": str(tariff_periods_path),
            "municipalities_path": str(municipalities_path),
            "building_properties_path": str(building_properties_path),
            "heat_pump_properties_path": str(heat_pump_properties_path),
        }
    )
    return results


# Architecture: Resolve the configuration source selected for this run.

def _config_path(
    run_context: RunContext,
    settings: Mapping[str, Any],
) -> Path:
    configured_path = settings.get("config_path")
    if configured_path is not None:
        return resolve_path(run_context.repository_root, configured_path)
    return run_context.input_root / "config" / "config.yml"


# Architecture: Validate required configuration paths and settings before initialization.

def _validate_settings(settings: Mapping[str, Any], config_path: Path) -> None:
    required = {
        "start_date",
        "project_lifetime_yrs",
        "delta_t",
        "type_of_cacer",
        "category_id",
        "filename_users_CACER_xls",
        "filename_giorni_tipo",
        "filename_comuni_italiani",
        "building_properties_folder",
        "hp_properties_folder",
        "provincia_it",
        "rand_factor",
        "rand_factor_noCER",
        "pv_derating_factor",
        "dod",
        "round_trip_efficiency",
        "battery_derating_factor",
    }
    missing = sorted(required.difference(settings))
    if missing:
        raise ValueError(f"Missing required settings in {config_path}: {missing}")
    if int(settings["project_lifetime_yrs"]) <= 0:
        raise ValueError("project_lifetime_yrs must be greater than zero")
    if not isinstance(settings["category_id"], Mapping):
        raise ValueError("category_id must be a mapping")


# Architecture: Persist normalized configuration artifacts for reproducible downstream use.

def _save_configuration_snapshot(
    output_path: Path,
    normalized: Any,
) -> tuple[Path, ...]:
    output_path.mkdir(parents=True, exist_ok=True)
    paths = {
        "configuration": output_path / "configuration.yml",
        "calendar": output_path / "calendar.csv",
        "monthly_calendar": output_path / "monthly_calendar.csv",
        "user_types": output_path / "registry_user_types.yml",
        "users": output_path / "registry_users.yml",
        "users_csv": output_path / "registry_users.csv",
        "plants": output_path / "registry_plants.yml",
        "plants_csv": output_path / "registry_plants.csv",
        "recap": output_path / "recap.yml",
        "membership": output_path / "membership_matrix.csv",
        "user_entry": output_path / "user_entry_matrix.csv",
        "plant_operation": output_path / "plant_operation_matrix.xlsx",
    }

    for key, value in (
        ("configuration", normalized.settings),
        ("user_types", normalized.registries.user_types),
        ("users", normalized.registries.users),
        ("plants", normalized.registries.plants),
        ("recap", normalized.recap),
    ):
        with paths[key].open("w", encoding="utf-8") as stream:
            yaml.safe_dump(dict(value), stream)

    normalized.calendars.calendar.to_csv(paths["calendar"], index=False)
    normalized.calendars.monthly_calendar.to_csv(
        paths["monthly_calendar"],
        index=True,
    )
    pd.DataFrame.from_dict(normalized.registries.users, orient="index").to_csv(
        paths["users_csv"]
    )
    plants = pd.DataFrame.from_dict(
        normalized.registries.plants,
        orient="index",
    )
    plant_specific = [
        column
        for column in ("titolare_POD", "installed_capacity")
        if column in plants.columns
    ]
    base_columns = sorted(
        column
        for column in plants.columns
        if column not in plant_specific
    )
    plants.index.name = "plant_id"
    plants.loc[:, base_columns + plant_specific].to_csv(paths["plants_csv"])
    normalized.matrices.membership.to_csv(paths["membership"])
    normalized.matrices.user_entry.to_csv(paths["user_entry"])
    with pd.ExcelWriter(paths["plant_operation"], engine="xlsxwriter") as writer:
        normalized.matrices.plant_type_operation.to_excel(
            writer,
            sheet_name="plant_type_operation_matrix",
        )
        normalized.matrices.plant_operation.to_excel(
            writer,
            sheet_name="plant_operation_matrix",
        )
    return tuple(paths.values())


# Architecture: Load optional property catalogs used to build typed domain objects.

def _load_property_catalog(
    directory: Path,
    model_type: type[BuildingProperties] | type[HeatPumpProperties],
) -> dict[str, Any]:
    if not directory.is_dir():
        raise FileNotFoundError(f"Configuration directory not found: {directory}")
    catalog: dict[str, Any] = {}
    for path in sorted(directory.glob("*.yml")):
        catalog[path.stem] = model_type.model_validate(load_yaml(path))
    if not catalog:
        raise ValueError(f"No YAML configuration files found in {directory}")
    return catalog
