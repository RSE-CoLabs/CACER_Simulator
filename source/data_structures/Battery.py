# Architecture: Define the validated battery configuration passed into energy-flow calculations.

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
# Architecture: Store immutable battery sizing, efficiency, and degradation parameters.

class Battery:
    """Electrical battery configuration.

    Capacity is expressed in kWh. Energy and state-of-charge time series are
    expected to use the simulation index frequency.
    """

    owner_id: str
    capacity_kwh: float
    depth_of_discharge: float
    round_trip_efficiency: float
    derating_factor_per_cycle: float

    def __post_init__(self) -> None:
        if self.capacity_kwh < 0:
            raise ValueError("Battery capacity must be non-negative")
        if not 0 <= self.depth_of_discharge <= 1:
            raise ValueError("Depth of discharge must be between 0 and 1")
        if not 0 < self.round_trip_efficiency <= 1:
            raise ValueError("Round-trip efficiency must be in (0, 1]")
        if not 0 <= self.derating_factor_per_cycle <= 1:
            raise ValueError("Battery derating factor must be between 0 and 1")
