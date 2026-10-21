# Architecture: Define typed containers for billing, ownership, incentives, cash flows, and financial indicators.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
# Architecture: Carry user-level and aggregated electricity-billing tables.

class BillingResults:
    """Per-user-type and aggregated electricity-bill tables."""

    user_bills: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    aggregated_bills: Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )


@dataclass(frozen=True, slots=True)
# Architecture: Carry PZO prices, RID revenues, GSE fees, and CACER revenue aggregates.

class RidResults:
    """PZO, RID revenue, and GSE fee tables."""

    pzo_hourly: Any
    monthly_revenue: Any
    gse_fees: Any
    aggregated_revenue: Any


@dataclass(frozen=True, slots=True)
# Architecture: Carry subscriptions, investment shares, ownership allocations, and CAPEX breakdowns.

class OwnershipResults:
    """Subscription, ownership, investment, repartition, and CAPEX tables."""

    subscription: Any
    ownership: Mapping[str, Any]
    investment: Any
    repartition: Mapping[str, Any]
    plant_capex: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
# Architecture: Carry monthly and configuration-level incentive, valorization, surplus, and fee data.

class IncentiveResults:
    """Monthly incentive, valorizzazione, surplus, and fee tables."""

    monthly: Any
    by_configuration: Any
    cacer_fees: float


@dataclass(frozen=True, slots=True)
# Architecture: Carry plant, user, configuration, and project cash-flow tables.

class CashFlowResults:
    """Plant, user, configuration, and project cash-flow tables."""

    plants: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    users: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    configurations: Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )
    project: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
# Architecture: Carry discounted-cash-flow tables and investment indicators.

class FinancialIndicators:
    """DCF and project financial indicators."""

    dcf_monthly: Any
    dcf_yearly: Any
    npv: float
    irr: float
    payback_period: float
    reporting_tables: Mapping[str, Any] = field(default_factory=dict)
