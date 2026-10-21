# Architecture: Define validated building properties and the thermal model used by HVAC simulation.

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
from pydantic import BaseModel, Field, field_validator


# Architecture: Validate and store the physical building parameters used by the thermal model.

class BuildingProperties(BaseModel):
    ks_gla: float = Field(..., description="Glazed-surface solar gain fraction [-].")
    ks_opa: float = Field(..., description="Opaque-surface solar gain fraction [-].")
    ks_infra: float = Field(..., description="Infrared contribution coefficient [-].")
    Volume: float = Field(..., description="Conditioned building volume [m3].")
    A_heated: float = Field(..., description="Conditioned floor area [m2].")
    A_walls: list[float] = Field(
        ...,
        description="Net external wall areas by eight cardinal orientations [m2].",
    )
    U_walls: float = Field(..., description="Wall thermal transmittance [W/(m2 K)].")
    U_windows: float = Field(
        ...,
        description="Window thermal transmittance [W/(m2 K)].",
    )
    U_roof: float = Field(..., description="Roof thermal transmittance [W/(m2 K)].")
    U_ground: float = Field(
        ...,
        description="Ground-floor thermal transmittance [W/(m2 K)].",
    )
    A_windows: list[float] = Field(
        ...,
        description="Net window areas by eight cardinal orientations [m2].",
    )
    ACR: float = Field(..., description="Air change rate [1/h].")
    C_m_walls: float = Field(..., description="Wall thermal capacity [J/(K m2)].")
    C_m_roof: float = Field(..., description="Roof thermal capacity [J/(K m2)].")
    C_m_floor: float = Field(..., description="Floor thermal capacity [J/(K m2)].")
    C_m_partitions: float = Field(
        ...,
        description="Partition thermal capacity [J/(K m2)].",
    )
    A_partitions: float = Field(..., description="Conditioned partition area [m2].")
    Reflectance: float = Field(..., description="Wall reflectance [-].")
    F_f: float = Field(..., description="Glazed fraction of window area [-].")
    C_s: float = Field(..., description="Light-element thermal capacity [J/(K m2)].")
    A_s: float = Field(..., description="Light-element surface area [m2].")
    A_window_frame: float = Field(..., description="Window-frame area [m2].")

    @field_validator(
        "ks_gla",
        "ks_opa",
        "ks_infra",
        "Volume",
        "A_heated",
        "U_walls",
        "U_windows",
        "U_roof",
        "U_ground",
        "C_m_walls",
        "C_m_roof",
        "C_m_floor",
    )
    @classmethod
    def must_be_non_negative(cls, value: float, info: Any) -> float:
        if value < 0:
            raise ValueError(f"{info.field_name} must be non-negative")
        return value


# Architecture: Expose the building thermal state-space representation consumed by HVAC calculations.

class BuildingModel:
    """Legacy three-node building model constructed from supplied values.

    ``simulation_interval`` is the expected time-series index frequency and
    retains the legacy ``"1H"``/otherwise-15-minute behavior.
    """

    def __init__(
        self,
        building_properties: BuildingProperties | Mapping[str, Any],
        simulation_interval: str,
    ) -> None:
        node_count = 3
        h_tr_is = 3.45
        h_tr_ms = 9.1
        cp_air = 1000
        rho_air = 1.2
        props = (
            building_properties
            if isinstance(building_properties, BuildingProperties)
            else BuildingProperties.model_validate(building_properties)
        )

        self.properties = props
        self.simulation_interval = simulation_interval
        self.ks_gla = props.ks_gla
        self.ks_opa = props.ks_opa
        self.ks_infra = props.ks_infra
        self.A_floor = props.A_heated
        self.A_partitions = props.A_partitions
        self.F_f = props.F_f
        self.U_walls = props.U_walls
        self.U_windows = props.U_windows
        self.U_roof = props.U_roof
        self.U_ground = props.U_ground

        tau = 3600 if simulation_interval == "1H" else 900
        self.opaque_area = (
            np.array(props.A_walls) * self.U_walls
            + np.array(props.A_windows) * (1 - self.F_f) * props.A_window_frame
        )
        self.opaque_area_roof = (
            self.A_floor / 8 * np.ones(8) * self.U_roof
        )
        self.glazed_area = np.array(props.A_windows)
        total_area = (
            np.sum(props.A_walls) + 2 * self.A_floor + self.A_partitions
        )
        self.V_heated = props.Volume
        self.H_tr_is = h_tr_is * total_area
        self.H_tr_w = props.U_windows * np.sum(props.A_windows)
        self.H_tr_op = (
            props.U_walls * np.sum(props.A_walls)
            + self.U_roof * self.A_floor
        )
        mass_area = np.sum(props.A_walls) + 2 * self.A_floor
        self.k_a = mass_area / total_area
        self.k_s = self.H_tr_w / (9.1 * total_area)
        self.H_tr_ms = h_tr_ms * mass_area
        self.H_tr_em = 1 / (1 / self.H_tr_op - 1 / self.H_tr_ms)
        self.H_ve = rho_air * cp_air * self.V_heated / 3600 * props.ACR
        self.C_m = (
            props.C_m_walls * (np.sum(props.A_walls) + self.A_partitions)
            + (props.C_m_roof + props.C_m_floor) * self.A_floor
        )
        self.C_s = props.A_s * props.C_s
        self.C_i = cp_air * rho_air * self.V_heated

        matrix = np.zeros([3, 3])
        matrix[0, 0] = -(self.H_tr_is + self.H_ve) - self.C_i / tau
        matrix[0, 1] = self.H_tr_is
        matrix[1, 0] = self.H_tr_is
        matrix[1, 1] = (
            -(self.H_tr_is + self.H_tr_w + self.H_tr_ms) - self.C_s / tau
        )
        matrix[1, 2] = self.H_tr_ms
        matrix[2, 1] = self.H_tr_ms
        matrix[2, 2] = -self.H_tr_em - self.H_tr_ms - self.C_m / tau

        inverse = np.linalg.inv(matrix)
        previous_state = np.array(
            [
                [-self.C_i / tau, 0, 0],
                [0, -self.C_s / tau, 0],
                [0, 0, -self.C_m / tau],
            ]
        )
        self.A = np.dot(inverse, previous_state)
        self.B = np.dot(inverse, np.eye(node_count))
