# Architecture: Define normalized generating-plant identity, ownership, capacity, and lifecycle data.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
# Architecture: Store immutable normalized plant identity, ownership, capacity, and lifecycle data.

class Plant:
    """Normalized generating plant.

    Installed, photovoltaic, and wind capacities retain the legacy kW units.
    Commissioning and exit values are month numbers in the simulation calendar.
    """

    plant_id: str
    owner_id: str
    installed_capacity_kw: float
    pv_capacity_kwp: float
    wind_capacity_kw: float
    battery_capacity_kwh: float
    commissioning_month: int
    exit_month: int | str
    attributes: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_registry(
        cls,
        plant_id: str,
        values: Mapping[str, Any],
    ) -> Plant:
        return cls(
            plant_id=plant_id,
            owner_id=str(values["titolare_POD"]),
            installed_capacity_kw=float(values["installed_capacity"]),
            pv_capacity_kwp=float(values["pv"]),
            wind_capacity_kw=float(values["wind"]),
            battery_capacity_kwh=float(values["battery"]),
            commissioning_month=int(values["commissioning_month"]),
            exit_month=values["exit_month"],
            attributes=dict(values),
        )
