# Architecture: Define validated heat-pump and HVAC domain objects consumed by thermal and HVAC calculations.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator

from source.data_structures.Building import BuildingModel, BuildingProperties


MODE_KEYS = (
    "alpha1_eff",
    "alpha2_eff",
    "alpha3_eff",
    "alpha4_eff",
    "alpha5_eff",
    "alpha6_eff",
    "alpha7_eff",
    "alpha8_eff",
    "alpha9_eff",
    "q_eff",
    "alpha1_power",
    "alpha2_power",
    "alpha3_power",
    "alpha4_power",
    "alpha5_power",
    "alpha6_power",
    "alpha7_power",
    "alpha8_power",
    "alpha9_power",
    "q_power",
    "r_sq",
    "p_th_max",
    "p_th_min",
    "p_th_nom",
    "p_nom",
    "T_setpoint_max",
    "f_min_EE",
    "f_seasonal_eta",
)
AUXILIARY_KEYS = (
    "Pel_fans",
    "eta_fans",
    "Pel_pumps",
    "eta_pumps",
    "V_tank",
    "cp_water",
    "rho_water",
    "q_heater",
    "T_cut_in",
    "T_dead_band",
)


# Architecture: Validate and store heat-pump performance and operating parameters.

class HeatPumpProperties(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    maker: str = Field(..., description="Heat-pump manufacturer.")
    model: str = Field(..., description="Heat-pump model.")
    Voltage: int = Field(..., description="Supply voltage [V].")
    I_c: float = Field(..., description="Compressor starting current [A].")
    phase: float = Field(..., description="Supply frequency [Hz].")
    starting_time: int = Field(..., description="Compressor startup duration [min].")
    thermal_storage: bool = Field(..., description="Thermal-storage availability.")
    heating_mode: dict[str, Any] = Field(
        ...,
        description="Heating performance coefficients and powers [W].",
    )
    cooling_mode: dict[str, Any] = Field(
        ...,
        description="Cooling performance coefficients and powers [W].",
    )
    auxiliaries: dict[str, Any] = Field(
        ...,
        description="Fan, pump, tank, and backup-heater parameters.",
    )

    @field_validator("I_c")
    @classmethod
    def validate_I_c(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Corrente di accensione deve essere maggiore di 0")
        return value

    @field_validator("Voltage")
    @classmethod
    def validate_Voltage(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Tensione di alimentazione deve essere maggiore di 0")
        return value

    @field_validator("phase")
    @classmethod
    def validate_phase(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Fase non valida")
        return value

    @field_validator("starting_time")
    @classmethod
    def validate_starting_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Tempo di avvio deve essere maggiore di 0")
        return value

    @field_validator("heating_mode")
    @classmethod
    def validate_heating_mode(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_numeric_keys(value, MODE_KEYS, "Heating mode")
        if value["p_th_max"] <= value["p_th_min"]:
            raise ValueError(
                "Potenza termica massima deve essere maggiore della potenza termica minima"
            )
        _validate_mode_bounds(value)
        return value

    @field_validator("cooling_mode")
    @classmethod
    def validate_cooling_mode(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_numeric_keys(value, MODE_KEYS, "Cooling mode")
        if value["p_th_max"] >= value["p_th_min"]:
            raise ValueError(
                "Potenza termica massima deve essere minore della potenza termica minima"
            )
        _validate_mode_bounds(value)
        return value

    @field_validator("auxiliaries")
    @classmethod
    def validate_auxiliaries(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_numeric_keys(value, AUXILIARY_KEYS, "Auxiliaries")
        return value


# Architecture: Define the shared heat-pump model contract for mode-specific implementations.

class HeatPumpModel:
    def __init__(
        self,
        hp_properties: HeatPumpProperties | Mapping[str, Any],
    ) -> None:
        self.properties = (
            hp_properties
            if isinstance(hp_properties, HeatPumpProperties)
            else HeatPumpProperties.model_validate(hp_properties)
        )
        self.maker = self.properties.maker
        self.model = self.properties.model
        self.I_c = self.properties.I_c
        self.Voltage = self.properties.Voltage
        self.phase = self.properties.phase
        self.starting_time = self.properties.starting_time
        self.thermal_storage = self.properties.thermal_storage


# Architecture: Represent cooling-mode heat-pump behavior parameters.

class CoolingModeHeatPump(HeatPumpModel):
    def __init__(
        self,
        hp_properties: HeatPumpProperties | Mapping[str, Any],
    ) -> None:
        super().__init__(hp_properties)
        self.hp_parameters = self.properties.cooling_mode
        self.f_min_EE = self.hp_parameters["f_min_EE"]
        self.f_seasonal_eta = self.hp_parameters["f_seasonal_eta"]
        self.P_th_max = self.hp_parameters["p_th_max"]
        self.P_th_min = self.hp_parameters["p_th_min"]
        self.T_setpoint_max = self.hp_parameters["T_setpoint_max"]


# Architecture: Represent heating-mode heat-pump behavior parameters.

class HeatingModeHeatPump(HeatPumpModel):
    def __init__(
        self,
        hp_properties: HeatPumpProperties | Mapping[str, Any],
    ) -> None:
        super().__init__(hp_properties)
        self.hp_parameters = self.properties.heating_mode
        self.f_min_EE = self.hp_parameters["f_min_EE"]
        self.f_seasonal_eta = self.hp_parameters["f_seasonal_eta"]
        self.P_th_max = self.hp_parameters["p_th_max"]
        self.P_th_min = self.hp_parameters["p_th_min"]
        self.T_setpoint_max = self.hp_parameters["T_setpoint_max"]


# Architecture: Represent auxiliary HVAC electrical loads associated with heat-pump operation.

class HeatPumpAuxiliaries(HeatPumpModel):
    def __init__(
        self,
        hp_properties: HeatPumpProperties | Mapping[str, Any],
    ) -> None:
        super().__init__(hp_properties)
        self.aux_parameters = self.properties.auxiliaries
        self.pel_fans = self.aux_parameters["Pel_fans"]
        self.eta_fans = self.aux_parameters["eta_fans"]
        self.pel_pumps = self.aux_parameters["Pel_pumps"]
        self.eta_pumps = self.aux_parameters["eta_pumps"]
        self.v_tank = self.aux_parameters["V_tank"]
        self.cp_water = self.aux_parameters["cp_water"]
        self.rho_water = self.aux_parameters["rho_water"]
        self.q_heater = self.aux_parameters["q_heater"]
        self.t_cut_in = self.aux_parameters["T_cut_in"]
        self.t_dead_band = self.aux_parameters["T_dead_band"]


@dataclass(slots=True)
# Architecture: Group heating, cooling, and auxiliary components into one HVAC unit.

class HVACUnit:
    """One building and heat-pump combination used by HVAC calculations."""

    name: str
    building: BuildingModel
    hp_heating: HeatingModeHeatPump
    hp_cooling: CoolingModeHeatPump
    hp_aux: HeatPumpAuxiliaries


@dataclass(slots=True)
# Architecture: Bind a normalized user to building and HVAC data for simulation.

class HPUser:
    """HVAC user assembled from already-loaded configuration values."""

    user_name: str
    user_type: str
    user_numbers: int
    p_contr: str
    condominium: bool
    location: str
    denomination: str
    hvac_type: str
    th_comfort_heating: float
    th_comfort_cooling: float
    users: tuple[HVACUnit, ...] = ()

    @property
    def buildings(self) -> tuple[BuildingModel, ...]:
        return tuple(user.building for user in self.users)

    @property
    def hp_heating(self) -> HeatingModeHeatPump | None:
        return self.users[0].hp_heating if self.users else None

    @property
    def hp_cooling(self) -> CoolingModeHeatPump | None:
        return self.users[0].hp_cooling if self.users else None

    @property
    def hp_aux(self) -> HeatPumpAuxiliaries | None:
        return self.users[0].hp_aux if self.users else None

    @classmethod
    def from_values(
        cls,
        user_name: str,
        user_properties: Mapping[str, Any],
        building_properties: list[BuildingProperties],
        heat_pump_properties: HeatPumpProperties,
        simulation_interval: str,
    ) -> HPUser:
        user_numbers = (
            1
            if user_properties["hvac_type"] == "autonomous"
            else int(user_properties["num"])
        )
        hp_heating = HeatingModeHeatPump(heat_pump_properties)
        hp_cooling = CoolingModeHeatPump(heat_pump_properties)
        hp_aux = HeatPumpAuxiliaries(heat_pump_properties)
        users = tuple(
            HVACUnit(
                name=user_name,
                building=BuildingModel(properties, simulation_interval),
                hp_heating=hp_heating,
                hp_cooling=hp_cooling,
                hp_aux=hp_aux,
            )
            for properties in building_properties
        )
        return cls(
            user_name=user_name,
            user_type=str(user_properties["type"]),
            user_numbers=user_numbers,
            p_contr=str(user_properties["power_range"]),
            condominium=bool(user_properties["condominium"]),
            location=str(user_properties["location"]),
            denomination=str(user_properties["denomination"]),
            hvac_type=str(user_properties["hvac_type"]),
            th_comfort_heating=float(user_properties["th_comfort_heating"]),
            th_comfort_cooling=float(user_properties["th_comfort_cooling"]),
            users=users,
        )


# Architecture: Validate numeric-keyed heat-pump mappings before model construction.

def _validate_numeric_keys(
    value: Mapping[str, Any],
    required_keys: tuple[str, ...],
    label: str,
) -> None:
    for key in required_keys:
        if key not in value:
            raise ValueError(f"{label} must have '{key}'")
    for key, item in value.items():
        if not isinstance(item, (float, int)):
            raise ValueError(f"{key} in {label.lower()} must be a number")


# Architecture: Validate operating bounds shared by heating and cooling modes.

def _validate_mode_bounds(value: Mapping[str, Any]) -> None:
    if value["r_sq"] < 0 or value["r_sq"] > 1:
        raise ValueError("R quadro deve essere compreso tra 0 e 1")
    if value["T_setpoint_max"] < 0:
        raise ValueError(
            "Temperatura di setpoint massima deve essere non negativa"
        )
