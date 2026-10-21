from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import pickle
from typing import Any

import pandas as pd
import pandapower as pp

from source.config.utilities import resolve_path
from source.data_structures import (
    ConfigResults,
    EnergyResults,
    GridResults,
    PipelineOptions,
    RunContext,
)
from source.grid.analysis import summarize_violations
from source.grid.load_flow import load_flow_simulator
from source.grid.network import NetworkInputs, create_network


NETWORK_SHEETS = {
    "buses": "bus",
    "external_grid": "ext_grid",
    "transformers": "branch(trafo)",
    "lines": "branch(line)",
    "switches": "switch",
    "loads": "load",
    "generators": "gen",
    "storage": "storage",
}


def run_grid_pipeline(
    run_context: RunContext,
    config_results: ConfigResults,
    upstream_results: Any | None = None,
    options: PipelineOptions | None = None,
) -> GridResults:
    """Run grid construction and load flow from in-memory energy results."""
    selected_options = options or run_context.options.grid
    if not selected_options.enabled:
        return GridResults(
            metadata={
                "domain": "grid",
                "enabled": False,
                "version": selected_options.version,
                "status": "disabled",
            }
        )
    if not isinstance(upstream_results, EnergyResults):
        raise TypeError("Grid pipeline requires upstream EnergyResults")

    settings = selected_options.settings
    workbook_path = _grid_workbook_path(run_context, config_results, settings)
    inputs = load_network_inputs(workbook_path)
    network_mode = str(settings.get("network_mode", "create")).lower()
    if network_mode == "create":
        network = create_network(
            str(settings.get("network_name", "example")),
            float(settings.get("frequency_hz", 50)),
            inputs,
            flag_gen=bool(settings.get("include_generators", False)),
        )
    elif network_mode == "external":
        network_path = settings.get("network_path")
        if network_path is None:
            raise ValueError("external network mode requires network_path")
        network = pp.from_pickle(
            str(resolve_path(run_context.repository_root, network_path))
        )
    else:
        raise ValueError("network_mode must be create or external")

    load_flow_mode = str(settings.get("load_flow_mode", "disabled")).lower()
    if load_flow_mode == "execute":
        exchange = energy_exchange_profiles(upstream_results)
        exchange = map_exchange_to_grid_pods(
            exchange,
            inputs.loads,
            settings.get("pod_profile_by_type"),
        )
        _validate_required_pods(inputs.loads, exchange)
        results = load_flow_simulator(
            network,
            inputs.loads,
            exchange,
            resample_interval=settings.get("resample_interval", "1h"),
        )
    elif load_flow_mode == "external":
        external_results = settings.get("external_results")
        if not isinstance(external_results, Mapping):
            raise ValueError(
                "external load-flow mode requires external_results mapping"
            )
        results = dict(external_results)
    elif load_flow_mode == "disabled":
        results = {}
    else:
        raise ValueError(
            "load_flow_mode must be execute, external, or disabled"
        )
    analyses = summarize_violations(results) if results else {}
    artifacts = save_grid_outputs(
        run_context.grid_output,
        network,
        results,
        analyses,
    )
    return GridResults(
        network=network,
        time_series=results,
        analyses=analyses,
        artifacts=artifacts,
        metadata={
            "domain": "grid",
            "enabled": True,
            "version": selected_options.version or "legacy",
            "status": "completed",
            "network_mode": network_mode,
            "load_flow_mode": load_flow_mode,
            "workbook_path": str(workbook_path),
            "element_counts": network_element_counts(network),
        },
    )


def load_network_inputs(path: Path) -> NetworkInputs:
    """Load the grid workbook once at the pipeline boundary."""
    workbook = pd.ExcelFile(path)
    sheets = {
        sheet: pd.read_excel(workbook, sheet_name=sheet)
        for sheet in NETWORK_SHEETS.values()
        if sheet in workbook.sheet_names
    }
    return NetworkInputs(
        **{
            field: sheets.get(sheet, pd.DataFrame())
            for field, sheet in NETWORK_SHEETS.items()
        }
    )


def energy_exchange_profiles(results: EnergyResults) -> pd.DataFrame:
    """Adapt per-user energy flows to positive-withdrawal grid profiles."""
    user_flows = results.flows.get("users")
    if not isinstance(user_flows, Mapping) or not user_flows:
        raise ValueError("EnergyResults.flows['users'] is required by grid")
    profiles: dict[str, pd.Series] = {}
    for user_id, frame in user_flows.items():
        if not isinstance(frame, pd.DataFrame):
            raise TypeError(f"Energy flow for {user_id} must be a DataFrame")
        missing = {"Eprel", "Eimm"}.difference(frame.columns)
        if missing:
            raise ValueError(f"Energy flow for {user_id} misses {sorted(missing)}")
        profiles[str(user_id)] = (
            frame["Eprel"].fillna(0).astype(float)
            - frame["Eimm"].fillna(0).astype(float)
        )
    exchange = pd.DataFrame(profiles)
    exchange.index = pd.to_datetime(exchange.index)
    exchange.index.name = "datetime"
    return exchange


def map_exchange_to_grid_pods(
    exchange: pd.DataFrame,
    load_mapping: pd.DataFrame,
    profile_by_type: Any,
) -> pd.DataFrame:
    """Expand representative profiles to PODs using an explicit type map."""
    if profile_by_type is None:
        return exchange
    if not isinstance(profile_by_type, Mapping):
        raise TypeError("pod_profile_by_type must be a mapping")
    required_columns = {"id_pod", "type"}
    missing_columns = required_columns.difference(load_mapping.columns)
    if missing_columns:
        raise ValueError(
            "Grid load mapping misses columns required for POD profile "
            f"assignment: {sorted(missing_columns)}"
        )
    mapped = exchange.copy()
    for row in load_mapping[["id_pod", "type"]].dropna(
        subset=["id_pod"]
    ).itertuples(index=False):
        pod_id = str(row.id_pod)
        if pod_id in mapped:
            continue
        user_type = str(row.type)
        source = profile_by_type.get(user_type)
        if source is None:
            raise ValueError(
                f"No POD profile mapping configured for grid type {user_type!r}"
            )
        source_id = str(source)
        if source_id not in exchange:
            raise ValueError(
                f"POD profile mapping for {user_type!r} references missing "
                f"energy profile {source_id!r}"
            )
        mapped[pod_id] = exchange[source_id]
    return mapped


def network_element_counts(network) -> dict[str, int]:
    return {
        name: len(network[name])
        for name in (
            "bus",
            "ext_grid",
            "trafo",
            "line",
            "switch",
            "load",
            "sgen",
            "gen",
            "storage",
        )
    }


def save_grid_outputs(
    output_path: Path,
    network,
    results: Mapping[str, pd.DataFrame],
    analyses: Mapping[str, Any],
) -> tuple[Path, ...]:
    network_path = output_path / "network.p"
    pp.to_pickle(network, str(network_path))
    artifacts = [network_path]
    if not results:
        return tuple(artifacts)
    results_path = output_path / "time_series.pkl"
    analysis_path = output_path / "violation_summary.csv"
    with results_path.open("wb") as stream:
        pickle.dump(dict(results), stream)
    pd.DataFrame(
        {
            key: [value]
            for key, value in analyses.items()
            if isinstance(value, (bool, int))
        }
    ).to_csv(analysis_path, index=False)
    artifacts.extend((results_path, analysis_path))
    return tuple(artifacts)


def _validate_required_pods(
    load_mapping: pd.DataFrame,
    exchange: pd.DataFrame,
) -> None:
    required = set(load_mapping["id_pod"].dropna().astype(str))
    missing = sorted(required.difference(exchange.columns))
    if missing:
        preview = ", ".join(missing[:5])
        suffix = "..." if len(missing) > 5 else ""
        raise ValueError(
            f"EnergyResults misses {len(missing)} grid POD profiles: "
            f"{preview}{suffix}"
        )


def _grid_workbook_path(
    run_context: RunContext,
    config_results: ConfigResults,
    settings: Mapping[str, Any],
) -> Path:
    configured = settings.get("workbook_path")
    if configured is not None:
        return resolve_path(run_context.repository_root, configured)
    migrated = run_context.input_root / "grid" / "example_network.xlsx"
    if migrated.exists():
        return migrated
    return resolve_path(
        run_context.repository_root,
        config_results.configuration["filename_data"],
    )
