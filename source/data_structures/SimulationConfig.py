# Architecture: Define normalized, path-independent simulation settings used by configuration and energy stages.

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Mapping

import pandas as pd


@dataclass(frozen=True, slots=True)
# Architecture: Store normalized path-independent settings shared by simulation calculations.

class SimulationConfig:
    """Path-independent simulation settings.

    ``index_frequency`` is the expected pandas frequency for all domain time
    series. Financial and registry matrices use one-based simulation months.
    """

    start_date: date
    project_lifetime_years: int
    index_frequency: str
    cacer_type: str
    province: str
    random_load_factor_percent: float
    random_non_cacer_factor_percent: float
    values: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> SimulationConfig:
        start = values["start_date"]
        if isinstance(start, datetime):
            start = start.date()
        elif not isinstance(start, date):
            start = date.fromisoformat(str(start))
        lifetime = int(values["project_lifetime_yrs"])
        if lifetime <= 0:
            raise ValueError("project_lifetime_yrs must be greater than zero")
        frequency = str(values["delta_t"])
        interval = pd.Timedelta(frequency)
        if interval <= pd.Timedelta(0):
            raise ValueError("delta_t must be greater than zero")
        return cls(
            start_date=start,
            project_lifetime_years=lifetime,
            index_frequency=frequency,
            cacer_type=str(values["type_of_cacer"]),
            province=str(values["provincia_it"]),
            random_load_factor_percent=float(values["rand_factor"]),
            random_non_cacer_factor_percent=float(values["rand_factor_noCER"]),
            values=dict(values),
        )
