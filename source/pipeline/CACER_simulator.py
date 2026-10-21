from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

import pandas as pd

from source.config import run_config_pipeline
from source.data_structures import (
    ConfigResults,
    EnergyResults,
    FinanceResults,
    GridResults,
    LoadResults,
    ReportingResults,
    RunContext,
    SimulationOptions,
    SimulationResults,
)
from source.energy import run_energy_pipeline
from source.finance import run_finance_pipeline
from source.grid import run_grid_pipeline
from source.load import run_load_pipeline
from source.pipeline.reporting_pipeline import run_reporting_pipeline


RUN_SUMMARY_NAME = "run_summary.json"


def run_simulation(
    repository_root: str | Path | None = None,
    *,
    input_root: str | Path | None = None,
    output_root: str | Path | None = None,
    options: SimulationOptions | None = None,
    random_seed: int | None = None,
    execution_metadata: Mapping[str, Any] | None = None,
    external_results: Mapping[str, Any] | None = None,
) -> SimulationResults:
    """Run every simulation stage and persist an explicit final status."""
    run_context = RunContext.create(
        repository_root,
        input_root=input_root,
        output_root=output_root,
        options=options,
        random_seed=random_seed,
        execution_metadata=execution_metadata,
    )
    summary = _initial_summary(run_context)
    summary_path = run_context.run_output / RUN_SUMMARY_NAME
    _write_summary(summary_path, summary)
    current_stage = "initialization"
    stage_started = perf_counter()

    try:
        supplied = external_results or {}
        if not isinstance(supplied, Mapping):
            raise TypeError("external_results must be a mapping")

        current_stage = "config"
        stage_started = perf_counter()
        config_results = run_config_pipeline(run_context)
        _complete_stage(summary, current_stage, config_results, stage_started)

        current_stage = "load"
        stage_started = perf_counter()
        if run_context.options.load.enabled:
            load_results = run_load_pipeline(run_context, config_results)
        else:
            load_results = _external_load_results(supplied.get("load"))
        _complete_stage(summary, current_stage, load_results, stage_started)

        current_stage = "energy"
        stage_started = perf_counter()
        energy_results = run_energy_pipeline(
            run_context,
            config_results,
            upstream_results=load_results,
        )
        _complete_stage(summary, current_stage, energy_results, stage_started)

        current_stage = "grid"
        stage_started = perf_counter()
        grid_results = run_grid_pipeline(
            run_context,
            config_results,
            upstream_results=energy_results,
        )
        _complete_stage(summary, current_stage, grid_results, stage_started)

        current_stage = "finance"
        stage_started = perf_counter()
        finance_results = run_finance_pipeline(
            run_context,
            config_results,
            upstream_results={
                "energy": energy_results,
                "grid": grid_results,
            },
        )
        _complete_stage(summary, current_stage, finance_results, stage_started)

        current_stage = "reporting"
        stage_started = perf_counter()
        reporting_results = run_reporting_pipeline(
            run_context,
            config_results,
            upstream_results={
                "load": load_results,
                "energy": energy_results,
                "grid": grid_results,
                "finance": finance_results,
            },
        )
        _complete_stage(summary, current_stage, reporting_results, stage_started)
    except Exception as error:
        summary["status"] = "failed"
        summary["failed_stage"] = current_stage
        summary["completed_at"] = _now()
        summary["exception"] = {
            "type": type(error).__name__,
            "message": str(error),
        }
        summary["stages"][current_stage] = {
            "status": "failed",
            "duration_seconds": round(perf_counter() - stage_started, 6),
        }
        _write_summary(summary_path, summary)
        raise

    summary["status"] = "completed"
    summary["completed_at"] = _now()
    summary["failed_stage"] = None
    _write_summary(summary_path, summary)
    return SimulationResults(
        context=run_context,
        config=config_results,
        load=load_results,
        energy=energy_results,
        grid=grid_results,
        finance=finance_results,
        reporting=reporting_results,
    )


def _external_load_results(value: Any) -> LoadResults:
    if not isinstance(value, LoadResults):
        raise ValueError(
            "Disabling the load pipeline requires external_results['load'] "
            "to be a LoadResults instance"
        )
    profiles = value.profiles.get("load")
    if not isinstance(profiles, pd.DataFrame):
        raise ValueError(
            "External LoadResults.profiles['load'] must be a pandas DataFrame"
        )
    return value


def _initial_summary(run_context: RunContext) -> dict[str, Any]:
    options = run_context.options
    return {
        "run_id": run_context.run_id,
        "status": "running",
        "failed_stage": None,
        "started_at": run_context.started_at.isoformat(),
        "completed_at": None,
        "random_seed": run_context.random_seed,
        "enabled_modules": list(options.enabled_modules),
        "selected_modes": {
            "config": {
                "enabled": options.config.enabled,
                "version": options.config.version or "native",
                "mode": "execute" if options.config.enabled else "disabled",
            },
            "load": {
                "enabled": options.load.enabled,
                "version": options.load.version,
                "mode": options.load.version,
            },
            "energy": {
                "enabled": options.energy.enabled,
                "version": options.energy.version,
                "hp_mode": options.energy.settings.get(
                    "hp_mode", "disabled"
                ),
                "pv_mode": options.energy.settings.get(
                    "pv_mode", "simulated"
                ),
                "battery_enabled": bool(
                    options.energy.settings.get("battery_enabled", True)
                ),
            },
            "grid": {
                "enabled": options.grid.enabled,
                "version": options.grid.version,
                "network_mode": options.grid.settings.get(
                    "network_mode", "create"
                ),
                "load_flow_mode": options.grid.settings.get(
                    "load_flow_mode", "disabled"
                ),
            },
            "finance": {
                "enabled": options.finance.enabled,
                "version": options.finance.version,
                "mode": options.finance.settings.get("mode", "disabled"),
            },
            "reporting": {
                "enabled": options.reporting.enabled,
                "version": options.reporting.version,
                "mode": options.reporting.settings.get("mode", "disabled"),
            },
        },
        "options": {
            "load_mode": options.load.version,
            "hp_mode": options.energy.settings.get("hp_mode"),
            "pv_mode": options.energy.settings.get("pv_mode"),
            "battery_enabled": options.energy.settings.get(
                "battery_enabled"
            ),
            "grid_enabled": options.grid.enabled,
            "finance_enabled": options.finance.enabled,
            "reporting_enabled": options.reporting.enabled,
        },
        "stages": {},
    }


def _complete_stage(
    summary: dict[str, Any],
    stage: str,
    results: (
        ConfigResults
        | LoadResults
        | EnergyResults
        | GridResults
        | FinanceResults
        | ReportingResults
    ),
    started: float,
) -> None:
    stage_summary = {
        "status": results.metadata.get("status", "completed"),
        "duration_seconds": round(perf_counter() - started, 6),
        "artifact_count": len(results.artifacts),
    }
    effective_keys = (
        "mode",
        "version",
        "hp_mode",
        "pv_mode",
        "battery_enabled",
        "network_mode",
        "load_flow_mode",
    )
    effective = {
        key: results.metadata[key]
        for key in effective_keys
        if key in results.metadata
    }
    if effective:
        stage_summary["effective_modes"] = effective
    summary["stages"][stage] = stage_summary


def _write_summary(path: Path, summary: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    results = run_simulation()
    print(f"Completed {results.context.run_id} at {results.context.run_output}")


if __name__ == "__main__":
    main()
