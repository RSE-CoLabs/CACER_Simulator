from __future__ import annotations

import calendar
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd

from source.data_structures import RidResults


@dataclass(frozen=True)
class Generator:
    name: str
    voltage: str
    capacity_kwp: float


@dataclass(frozen=True)
class RidFeeParameters:
    threshold_1: float
    threshold_2: float
    threshold_3: float
    maximum_fee: float


def calculate_rid(
    *,
    energy_user_flows: Mapping[str, pd.DataFrame],
    user_types: Mapping[str, Mapping[str, Any]],
    recap: Mapping[str, Any],
    municipalities: pd.DataFrame,
    province: str,
    start_date: str | date | datetime | pd.Timestamp,
    project_lifetime_years: int,
    pzo_input: pd.DataFrame,
    rid_assumptions: Mapping[str, Any],
    bt_losses: float,
    mt_losses: float,
) -> RidResults:
    """Calculate PZO profile, RID revenues, and annual GSE fees."""
    market_zone = get_market_zone(municipalities, province)
    pzo_profile = generate_pzo_profile(
        pzo_input,
        market_zone=market_zone,
        start_year=pd.Timestamp(start_date).year,
        project_lifetime_years=project_lifetime_years,
        yearly_variation=rid_assumptions["variazione_annua"],
    )
    generators = build_generators(user_types)
    monthly_revenue = compute_generator_revenues(
        generators=generators,
        energy_user_flows=energy_user_flows,
        pzo_profile=pzo_profile,
        bt_losses=bt_losses,
        mt_losses=mt_losses,
    )
    gse_fees = compute_generator_fees(
        generators=generators,
        fee_parameters=build_fee_parameters(
            rid_assumptions["corrispettivi_unitari"]["PV"]
        ),
    )
    aggregated_revenue = aggregate_cacer_revenues(monthly_revenue, recap)

    return RidResults(
        pzo_hourly=pzo_profile,
        monthly_revenue=monthly_revenue,
        gse_fees=gse_fees,
        aggregated_revenue=aggregated_revenue,
    )


def compute_generator_revenues(
    *,
    generators: Sequence[Generator],
    energy_user_flows: Mapping[str, pd.DataFrame],
    pzo_profile: pd.DataFrame,
    bt_losses: float,
    mt_losses: float,
) -> pd.DataFrame:
    """Compute monthly RID revenues for all generators."""
    if not generators:
        raise ValueError("RID calculation requires at least one generator")

    revenues = pd.DataFrame()
    pzo = pzo_profile["PZO"]

    for generator in generators:
        hourly_injection = compute_hourly_injection(
            flow=energy_user_flows[generator.name],
            voltage=generator.voltage,
            bt_losses=bt_losses,
            mt_losses=mt_losses,
        )
        if not pzo.index.equals(hourly_injection.index):
            raise ValueError(
                "PZO profile and hourly injection timestamps must match for "
                f"generator {generator.name!r}"
            )

        monthly_revenue = (pzo * hourly_injection).resample("ME").sum()
        if revenues.empty:
            revenues = pd.DataFrame(index=monthly_revenue.index)
        revenues[generator.name] = monthly_revenue

    revenues.index = revenues.index.strftime("%Y-%m")
    revenues.index.name = "month"
    return revenues


def compute_hourly_injection(
    *,
    flow: pd.DataFrame,
    voltage: str,
    bt_losses: float,
    mt_losses: float,
) -> pd.Series:
    """Apply technical losses and aggregate injections hourly."""
    losses = bt_losses if voltage.upper() == "BT" else mt_losses
    return flow["Eimm"].astype(float).mul(1 + losses).resample("1h").sum()


def aggregate_cacer_revenues(
    monthly_revenue: pd.DataFrame,
    recap: Mapping[str, Any],
) -> pd.DataFrame:
    """Aggregate generator revenues at CACER level."""
    aggregated = monthly_revenue.copy()
    cacer_name = str(recap["type_of_cacer"])
    cacer_generators = set(recap["list_types_prosumers_CACER"]) | set(
        recap["list_types_producers_CACER"]
    )
    aggregated[cacer_name] = aggregated[
        [name for name in aggregated.columns if name in cacer_generators]
    ].sum(axis=1)
    return aggregated


def compute_generator_fees(
    *,
    generators: Sequence[Generator],
    fee_parameters: RidFeeParameters,
) -> pd.DataFrame:
    """Compute annual RID fees."""
    fees = {
        generator.name: rid_gse_fee(
            generator.capacity_kwp,
            fee_parameters,
        )
        for generator in generators
    }
    return pd.DataFrame(fees, index=["GSE_fees"])


def rid_gse_fee(
    generation_capacity_kwp: float,
    fee_parameters: RidFeeParameters,
) -> float:
    """Compute the annual GSE RID fee."""
    fee = min(generation_capacity_kwp, 20) * fee_parameters.threshold_1
    fee += (
        max(0.0, min(generation_capacity_kwp - 20, 200))
        * fee_parameters.threshold_2
    )
    fee += (
        max(0.0, generation_capacity_kwp - 200)
        * fee_parameters.threshold_3
    )
    return min(fee, fee_parameters.maximum_fee)


def generate_pzo_profile(
    pzo_input: pd.DataFrame,
    *,
    market_zone: str,
    start_year: int,
    project_lifetime_years: int,
    yearly_variation: Sequence[float],
) -> pd.DataFrame:
    """Expand one historical PZO profile over the project lifetime."""
    if project_lifetime_years < 1:
        raise ValueError("project_lifetime_years must be at least one")
    if len(yearly_variation) < project_lifetime_years:
        raise ValueError(
            "yearly_variation length is smaller than project lifetime"
        )

    source = pzo_input.copy()
    source.index = pd.to_datetime(
        source["Date"],
        format="mixed",
        dayfirst=False,
    )
    base_profile = source[market_zone].astype(float)
    frames: list[pd.Series] = []
    degradation_factor = 1.0

    for offset in range(project_lifetime_years):
        degradation_factor *= 1 - float(yearly_variation[offset])
        year = start_year + offset
        profile = _profile_for_year(base_profile, year)
        frames.append(profile * degradation_factor / 1000)

    result = pd.concat(frames).sort_index().to_frame("PZO")
    result.index.name = "datetime"
    return result


def _profile_for_year(base_profile: pd.Series, year: int) -> pd.Series:
    profile = base_profile.copy()
    source_has_leap_day = bool(
        ((profile.index.month == 2) & (profile.index.day == 29)).any()
    )

    if not calendar.isleap(year):
        profile = profile[
            ~((profile.index.month == 2) & (profile.index.day == 29))
        ]

    profile.index = profile.index.map(
        lambda timestamp: timestamp.replace(year=year)
    )

    if calendar.isleap(year) and not source_has_leap_day:
        february_28 = profile[
            (profile.index.month == 2) & (profile.index.day == 28)
        ].copy()
        february_28.index = february_28.index.map(
            lambda timestamp: timestamp.replace(day=29)
        )
        profile = pd.concat([profile, february_28])

    return profile


def build_generators(
    user_types: Mapping[str, Mapping[str, Any]],
) -> list[Generator]:
    """Convert configuration dictionaries into domain objects."""
    return [
        Generator(
            name=name,
            voltage=str(values["voltage"]),
            capacity_kwp=float(values["pv"]),
        )
        for name, values in user_types.items()
        if bool(values.get("producing"))
    ]


def build_fee_parameters(
    raw_inputs: Mapping[str, Any],
) -> RidFeeParameters:
    """Convert fee configuration into typed parameters."""
    return RidFeeParameters(
        threshold_1=float(raw_inputs["threshold_1"]),
        threshold_2=float(raw_inputs["threshold_2"]),
        threshold_3=float(raw_inputs["threshold_3"]),
        maximum_fee=float(raw_inputs["massimale"]),
    )


def get_market_zone(
    municipalities: pd.DataFrame,
    province: str,
) -> str:
    """Get the market zone associated with a province."""
    rows = municipalities[
        municipalities["Denominazione in italiano"] == province
    ]
    if rows.empty:
        raise ValueError(f"No market zone found for province {province!r}")
    return str(rows["Zona di mercato"].iloc[0])
