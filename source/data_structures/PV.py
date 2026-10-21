# Architecture: Define validated photovoltaic-system parameters used by generation modeling.

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
# Architecture: Store immutable photovoltaic capacity, orientation, mounting, and derating parameters.

class PV:
    """Photovoltaic plant configuration.

    Capacity is expressed in kWp; tilt and azimuth are expressed in degrees.
    Generated profiles are expected to use the simulation index frequency.
    """

    plant_id: str
    capacity_kwp: float
    tilt_degrees: float
    azimuth_degrees: float
    mounting: str | None
    derating_factor: float

    def __post_init__(self) -> None:
        if self.capacity_kwp < 0:
            raise ValueError("PV capacity must be non-negative")
        if self.derating_factor < 0:
            raise ValueError("PV derating factor must be non-negative")
