# Architecture: Re-export the shared configuration, domain, run-context, and result contracts.

"""Shared simulator data structures and pipeline contracts."""

from source.data_structures.Battery import Battery
from source.data_structures.Building import BuildingModel, BuildingProperties
from source.data_structures.Configuration import (
    CalendarData,
    Cacer,
    ConfigurationData,
    ConfigurationMatrices,
    DomainObjectRegistry,
    RegistryData,
)
from source.data_structures.HP import (
    CoolingModeHeatPump,
    HeatPumpAuxiliaries,
    HeatPumpModel,
    HeatPumpProperties,
    HVACUnit,
    HeatingModeHeatPump,
    HPUser,
)
from source.data_structures.Plant import Plant
from source.data_structures.PV import PV
from source.data_structures.Results import (
    ConfigResults,
    EnergyResults,
    FinanceResults,
    GridResults,
    LoadResults,
    ReportingResults,
    SimulationResults,
)
from source.data_structures.Finance import (
    BillingResults,
    CashFlowResults,
    FinancialIndicators,
    IncentiveResults,
    OwnershipResults,
    RidResults,
)
from source.data_structures.RunContext import (
    PipelineOptions,
    RunContext,
    SimulationOptions,
)
from source.data_structures.SimulationConfig import SimulationConfig
from source.data_structures.User import User

__all__ = [
    "Battery",
    "BuildingModel",
    "BuildingProperties",
    "CalendarData",
    "Cacer",
    "CoolingModeHeatPump",
    "ConfigurationData",
    "ConfigurationMatrices",
    "ConfigResults",
    "DomainObjectRegistry",
    "EnergyResults",
    "FinanceResults",
    "BillingResults",
    "RidResults",
    "OwnershipResults",
    "IncentiveResults",
    "CashFlowResults",
    "FinancialIndicators",
    "GridResults",
    "HeatPumpAuxiliaries",
    "HeatPumpModel",
    "HeatPumpProperties",
    "HVACUnit",
    "HeatingModeHeatPump",
    "HPUser",
    "LoadResults",
    "PipelineOptions",
    "Plant",
    "PV",
    "ReportingResults",
    "RegistryData",
    "RunContext",
    "SimulationConfig",
    "SimulationOptions",
    "SimulationResults",
    "User",
]
