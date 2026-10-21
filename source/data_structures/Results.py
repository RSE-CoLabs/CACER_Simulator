# Architecture: Define typed result boundaries for every simulation stage and the aggregate run.

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from source.data_structures.Configuration import ConfigurationData


@dataclass(slots=True)
# Architecture: Carry normalized configuration data and configuration-stage artifacts.

class ConfigResults:
    """Configuration outputs; calendar tables use the configured index frequency."""

    configuration: Mapping[str, Any] = field(default_factory=dict)
    calendars: Mapping[str, Any] = field(default_factory=dict)
    registries: Mapping[str, Any] = field(default_factory=dict)
    data_structures: Mapping[str, Any] = field(default_factory=dict)
    normalized: ConfigurationData | None = None
    artifacts: tuple[Path, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
# Architecture: Carry user load profiles, schedules, and load-stage artifacts.

class LoadResults:
    """Load tables in kWh per simulation interval, indexed by simulation time."""

    profiles: Mapping[str, Any] = field(default_factory=dict)
    schedules: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[Path, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
# Architecture: Carry PV, HVAC, user-flow, aggregate-flow, and shared-energy outputs.

class EnergyResults:
    """Energy tables in kWh per simulation interval, indexed by simulation time."""

    flows: Mapping[str, Any] = field(default_factory=dict)
    production: Mapping[str, Any] = field(default_factory=dict)
    hvac: Mapping[str, Any] = field(default_factory=dict)
    incentives: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[Path, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
# Architecture: Carry the network, time-series power-flow outputs, and grid analyses.

class GridResults:
    """Grid tables indexed by simulation time; units remain column-specific."""

    network: Any | None = None
    time_series: Mapping[str, Any] = field(default_factory=dict)
    analyses: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[Path, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
# Architecture: Carry billing, incentives, ownership, cash-flow, and indicator outputs.

class FinanceResults:
    """Financial tables in their legacy currency units and monthly/yearly indices."""

    bills: Mapping[str, Any] = field(default_factory=dict)
    cash_flows: Mapping[str, Any] = field(default_factory=dict)
    incentives: Mapping[str, Any] = field(default_factory=dict)
    indicators: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[Path, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
# Architecture: Carry rendered figures, tables, documents, and reporting artifacts.

class ReportingResults:
    """References to figures, tables, documents, and their persisted artifacts."""
    figures: Mapping[str, Any] = field(default_factory=dict)
    tables: Mapping[str, Any] = field(default_factory=dict)
    documents: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[Path, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
# Architecture: Aggregate every stage result into the top-level simulator return value.

class SimulationResults:
    context: Any
    config: ConfigResults
    load: LoadResults
    energy: EnergyResults
    grid: GridResults
    finance: FinanceResults
    reporting: ReportingResults
