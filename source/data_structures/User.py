# Architecture: Define normalized user identity, participation, load, and production attributes.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
# Architecture: Store immutable normalized user identity, participation, and load/production attributes.

class User:
    """Normalized simulator user constructed from a registry entry.

    Contracted power is retained in its legacy textual range. Comfort
    temperatures are in degrees Celsius and entry/exit values are month
    numbers in the simulation calendar.
    """

    user_id: str
    user_type: str
    category: str
    type: str
    consuming: bool
    producing: bool
    entry_month: int
    exit_month: int | str
    location: str
    power_range: str
    heat_load: bool
    attributes: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_registry(
        cls,
        user_id: str,
        values: Mapping[str, Any],
    ) -> User:
        return cls(
            user_id=user_id,
            user_type=str(values["user_type"]),
            category=str(values["category"]),
            type=str(values["type"]),
            consuming=bool(values["consuming"]),
            producing=bool(values["producing"]),
            entry_month=int(values["entry_month"]),
            exit_month=values["exit_month"],
            location=str(values["location"]),
            power_range=str(values["power_range"]),
            heat_load=bool(values["heat_load"]),
            attributes=dict(values),
        )
