# Architecture: Define run-scoped paths, options, identifiers, and metadata shared by all pipelines.

from __future__ import annotations

import platform
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


DOMAIN_NAMES = ("config", "load", "energy", "grid", "finance", "reporting")
RUN_NAME_PATTERN = re.compile(r"^Run([1-9][0-9]*)$")


# Architecture: Freeze option mappings so stage configuration cannot change during a run.

def _immutable_mapping(values: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(values))


@dataclass(frozen=True, slots=True)
# Architecture: Describe enablement, version, mode-specific settings, and stage inputs.

class PipelineOptions:
    enabled: bool = True
    version: str | None = None
    settings: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "settings", _immutable_mapping(self.settings))


# Architecture: Define the default load-stage execution mode.

def _default_load_options() -> PipelineOptions:
    return PipelineOptions(version="emulator_v1")


# Architecture: Define the default energy-stage execution mode and feature flags.

def _default_energy_options() -> PipelineOptions:
    return PipelineOptions(
        version="legacy",
        settings={
            "hp_mode": "disabled",
            "pv_mode": "simulated",
            "battery_enabled": True,
        },
    )


# Architecture: Define the default grid-stage network and load-flow modes.

def _default_grid_options() -> PipelineOptions:
    return PipelineOptions(
        version="native",
        settings={
            "network_mode": "create",
            "load_flow_mode": "disabled",
        },
    )


# Architecture: Define the default finance-stage execution mode.

def _default_finance_options() -> PipelineOptions:
    return PipelineOptions(
        version="native",
        settings={"mode": "execute"},
    )


# Architecture: Define the default reporting-stage execution mode.

def _default_reporting_options() -> PipelineOptions:
    return PipelineOptions(
        version="native",
        settings={"mode": "execute"},
    )


@dataclass(frozen=True, slots=True)
# Architecture: Group validated options for every simulator pipeline.

class SimulationOptions:
    config: PipelineOptions = field(default_factory=PipelineOptions)
    load: PipelineOptions = field(default_factory=_default_load_options)
    energy: PipelineOptions = field(default_factory=_default_energy_options)
    grid: PipelineOptions = field(default_factory=_default_grid_options)
    finance: PipelineOptions = field(default_factory=_default_finance_options)
    reporting: PipelineOptions = field(
        default_factory=_default_reporting_options
    )

    @classmethod
    def from_modes(
        cls,
        *,
        load_mode: str = "emulator_v1",
        hp_mode: str = "disabled",
        pv_mode: str = "simulated",
        battery_enabled: bool = True,
        grid_enabled: bool = True,
        finance_enabled: bool = True,
        reporting_enabled: bool = True,
        load_settings: Mapping[str, Any] | None = None,
        energy_settings: Mapping[str, Any] | None = None,
        grid_settings: Mapping[str, Any] | None = None,
        finance_settings: Mapping[str, Any] | None = None,
        reporting_settings: Mapping[str, Any] | None = None,
    ) -> SimulationOptions:
        """Build validated pipeline options from the public simulation modes."""
        load_modes = {"emulator_v1", "emulator_v2", "external"}
        hp_modes = {"non_optimized", "optimized", "external", "disabled"}
        pv_modes = {"simulated", "external", "disabled"}
        if load_mode not in load_modes:
            raise ValueError(f"load_mode must be one of {sorted(load_modes)}")
        if hp_mode not in hp_modes:
            raise ValueError(f"hp_mode must be one of {sorted(hp_modes)}")
        if pv_mode not in pv_modes:
            raise ValueError(f"pv_mode must be one of {sorted(pv_modes)}")

        load_values = dict(load_settings or {})
        energy_values = dict(energy_settings or {})
        energy_values.update(
            {
                "hp_mode": hp_mode,
                "pv_mode": pv_mode,
                "battery_enabled": battery_enabled,
            }
        )
        return cls(
            load=PipelineOptions(
                version=load_mode,
                settings=load_values,
            ),
            energy=PipelineOptions(settings=energy_values),
            grid=PipelineOptions(
                enabled=grid_enabled,
                version="native",
                settings=dict(grid_settings or {}),
            ),
            finance=PipelineOptions(
                enabled=finance_enabled,
                version="native",
                settings={
                    "mode": "execute",
                    **dict(finance_settings or {}),
                },
            ),
            reporting=PipelineOptions(
                enabled=reporting_enabled,
                version="native",
                settings={
                    "mode": "execute",
                    **dict(reporting_settings or {}),
                },
            ),
        )

    @property
    def enabled_modules(self) -> tuple[str, ...]:
        return tuple(name for name in DOMAIN_NAMES if getattr(self, name).enabled)

    def for_domain(self, domain: str) -> PipelineOptions:
        if domain not in DOMAIN_NAMES:
            raise ValueError(f"Unknown simulation domain: {domain}")
        return getattr(self, domain)


@dataclass(frozen=True, slots=True)
# Architecture: Allocate run-scoped directories, identifiers, timestamps, and execution metadata.

class RunContext:
    run_id: str
    repository_root: Path
    input_root: Path
    output_root: Path
    run_output: Path
    config_output: Path
    load_output: Path
    energy_output: Path
    grid_output: Path
    finance_output: Path
    reporting_output: Path
    options: SimulationOptions
    random_seed: int | None
    started_at: datetime
    execution_metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None or self.started_at.utcoffset() is None:
            raise ValueError("started_at must be timezone-aware")
        if not RUN_NAME_PATTERN.fullmatch(self.run_id):
            raise ValueError("run_id must use the RunN format")
        object.__setattr__(
            self,
            "execution_metadata",
            _immutable_mapping(self.execution_metadata),
        )

    @classmethod
    def create(
        cls,
        repository_root: str | Path | None = None,
        *,
        input_root: str | Path | None = None,
        output_root: str | Path | None = None,
        options: SimulationOptions | None = None,
        random_seed: int | None = None,
        started_at: datetime | None = None,
        execution_metadata: Mapping[str, Any] | None = None,
    ) -> RunContext:
        repository = Path(repository_root or Path.cwd()).resolve()
        inputs = Path(input_root or repository / "input_data").resolve()
        outputs = Path(output_root or repository / "output_data").resolve()
        outputs.mkdir(parents=True, exist_ok=True)

        run_id, run_output = cls._allocate_run_directory(outputs)
        domain_outputs = {name: run_output / name for name in DOMAIN_NAMES}
        for path in domain_outputs.values():
            path.mkdir()

        metadata = {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "executable": sys.executable,
        }
        metadata.update(execution_metadata or {})

        return cls(
            run_id=run_id,
            repository_root=repository,
            input_root=inputs,
            output_root=outputs,
            run_output=run_output,
            config_output=domain_outputs["config"],
            load_output=domain_outputs["load"],
            energy_output=domain_outputs["energy"],
            grid_output=domain_outputs["grid"],
            finance_output=domain_outputs["finance"],
            reporting_output=domain_outputs["reporting"],
            options=options or SimulationOptions(),
            random_seed=random_seed,
            started_at=started_at or datetime.now(timezone.utc),
            execution_metadata=metadata,
        )

    @staticmethod
    def _allocate_run_directory(output_root: Path) -> tuple[str, Path]:
        existing_numbers = [
            int(match.group(1))
            for path in output_root.iterdir()
            if path.is_dir() and (match := RUN_NAME_PATTERN.fullmatch(path.name))
        ]
        candidate = max(existing_numbers, default=0) + 1
        while True:
            run_id = f"Run{candidate}"
            run_output = output_root / run_id
            try:
                run_output.mkdir()
            except FileExistsError:
                candidate += 1
                continue
            return run_id, run_output

    def output_for(self, domain: str) -> Path:
        if domain not in DOMAIN_NAMES:
            raise ValueError(f"Unknown simulation domain: {domain}")
        return getattr(self, f"{domain}_output")
