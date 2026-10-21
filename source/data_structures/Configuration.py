# Architecture: Define the normalized configuration containers exchanged between pipeline stages.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import pandas as pd

from source.data_structures.Battery import Battery
from source.data_structures.Building import BuildingProperties
from source.data_structures.HP import HeatPumpProperties
from source.data_structures.PV import PV
from source.data_structures.Plant import Plant
from source.data_structures.SimulationConfig import SimulationConfig
from source.data_structures.User import User


@dataclass(slots=True)
# Architecture: Group full-resolution and monthly simulation calendars.

class CalendarData:
    calendar: pd.DataFrame
    monthly_calendar: pd.DataFrame


@dataclass(slots=True)
# Architecture: Group normalized configuration registries shared across domains.

class RegistryData:
    user_types: dict[str, dict[str, Any]]
    users: dict[str, dict[str, Any]]
    cacer_users: dict[str, dict[str, Any]]
    plants: dict[str, dict[str, Any]]


@dataclass(slots=True)
# Architecture: Group membership, operation, and entry matrices that describe time-dependent participation.

class ConfigurationMatrices:
    """Monthly matrices indexed by entity and one-based simulation month."""

    membership: pd.DataFrame
    user_entry: pd.DataFrame
    plant_type_operation: pd.DataFrame
    plant_operation: pd.DataFrame


@dataclass(frozen=True, slots=True)
# Architecture: Store normalized CACER scenario and allocation metadata.

class Cacer:
    """Path-independent CACER configuration for HVAC domain construction."""

    cacer_type: str
    simulation_interval: str
    hp_user_types: tuple[str, ...]

    @classmethod
    def from_values(
        cls,
        cacer_type: str,
        simulation_interval: str,
        user_types: Mapping[str, Mapping[str, Any]],
    ) -> Cacer:
        return cls(
            cacer_type=cacer_type,
            simulation_interval=simulation_interval,
            hp_user_types=tuple(
                user_type
                for user_type, values in user_types.items()
                if bool(values["heat_load"]) and not bool(values["condominium"])
            ),
        )


@dataclass(slots=True)
# Architecture: Group typed runtime objects for users, plants, PV, storage, buildings, and HVAC.

class DomainObjectRegistry:
    simulation: SimulationConfig
    cacer: Cacer
    users: dict[str, User]
    plants: dict[str, Plant]
    photovoltaic: dict[str, PV]
    batteries: dict[str, Battery]
    building_properties: dict[str, BuildingProperties]
    heat_pump_properties: dict[str, HeatPumpProperties]


@dataclass(slots=True)
# Architecture: Provide the complete normalized configuration contract returned by initialization.

class ConfigurationData:
    settings: Mapping[str, Any]
    calendars: CalendarData
    registries: RegistryData
    matrices: ConfigurationMatrices
    domain_objects: DomainObjectRegistry
    recap: dict[str, Any] = field(default_factory=dict)
