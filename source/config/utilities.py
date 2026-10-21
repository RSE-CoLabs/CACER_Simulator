# Architecture: Provide shared path, file, calendar, and lookup services used across configuration and downstream stages.

from __future__ import annotations

import contextlib
import io
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping, TypeVar

import holidays
import pandas as pd
import yaml
from ruamel.yaml import YAML


T = TypeVar("T")


# Architecture: Resolve repository-relative and absolute paths at the configuration boundary.

def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(str(value).replace("\\", "/"))
    return path if path.is_absolute() else root / path


# Architecture: Load a YAML mapping used as structured configuration input.

def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return value


# Architecture: Persist a structured configuration mapping as YAML.

def save_yaml(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(dict(value), stream)


# Architecture: Generate the canonical timestamp and calendar metadata shared by stages.

def generate_calendar_modified(start_day: date, end_day: date) -> pd.DataFrame:
    start_date = start_day.strftime("%Y-%m-%d")
    end_date = (end_day + timedelta(days=1)).strftime("%Y-%m-%d")
    calendar = pd.DataFrame(
        {"datetime": pd.date_range(start=start_date, end=end_date, freq="15Min")}
    ).iloc[:-1]
    calendar["day_week"] = calendar.datetime.dt.dayofweek
    italian_holidays = holidays.IT()
    calendar["holiday"] = calendar["datetime"].apply(
        lambda timestamp: timestamp.date() in italian_holidays
    )
    calendar["day_flag"] = "Working_day"
    calendar.loc[calendar["day_week"] == 5, "day_flag"] = "Saturday"
    calendar.loc[calendar["day_week"] == 6, "day_flag"] = "Sunday"
    calendar.loc[calendar["holiday"], "day_flag"] = "Sunday"
    return calendar.drop(columns=["holiday"])


# Architecture: Map an Italian province to the region used by tariffs and weather inputs.

def province_to_region(
    province_it: str,
    italian_municipalities: pd.DataFrame,
) -> str:
    row = _municipality_row(province_it, italian_municipalities)
    return str(row["Denominazione Regione"])


# Architecture: Translate province labels for external data-provider interfaces.

def province_italian_to_english(
    province_it: str,
    italian_municipalities: pd.DataFrame,
) -> str:
    row = _municipality_row(province_it, italian_municipalities)
    return str(row["Denominazione provincia in inglese"])


# Architecture: Translate configured location labels for external data-provider interfaces.

def location_italian_to_english(
    location_it: str,
    italian_municipalities: pd.DataFrame,
) -> str:
    row = _municipality_row(location_it, italian_municipalities)
    return str(row["Denominazione provincia in inglese"])


# Architecture: Select the municipality reference row behind location conversions.

def _municipality_row(
    location_it: str,
    italian_municipalities: pd.DataFrame,
) -> pd.Series:
    matches = italian_municipalities[
        italian_municipalities["Denominazione in italiano"] == location_it
    ]
    if matches.empty:
        raise ValueError(f"Location not found in municipality data: {location_it}")
    return matches.iloc[0]


# Architecture: Create or validate a folder used for stage inputs or outputs.

def check_folder_exists(folder_path: str | Path) -> Path:
    path = Path(folder_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


# Architecture: Remove files from a targeted output folder before regeneration.

def clear_folder_content(folder_directory: str | Path) -> None:
    path = Path(folder_directory)
    for child in path.iterdir():
        if child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)


# Architecture: Update a nested configuration mapping with one explicit value.

def add_to_mapping(mapping: dict[str, Any], key: str, value: Any) -> None:
    mapping[key] = value


# Architecture: Update user-level financial configuration values in the source mapping.

def update_user_irr(
    recap: dict[str, Any],
    user_id: str,
    irr_value: float,
) -> None:
    irr = recap.setdefault("irr", {})
    if not isinstance(irr, dict):
        raise TypeError("recap['irr'] must be a mapping")
    irr[user_id] = irr_value


# Architecture: Add a value to a YAML-backed configuration mapping.

def add_to_yaml(
    path: str | Path,
    section: str | None,
    key: str,
    value: Any,
) -> None:
    yaml_editor = YAML()
    yaml_editor.preserve_quotes = True
    file_path = Path(path)
    with file_path.open("r", encoding="utf-8") as stream:
        data = yaml_editor.load(stream)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping in {file_path}")
    if section is None:
        data[key] = value
    else:
        section_data = data.setdefault(section, {})
        if not isinstance(section_data, dict):
            raise TypeError(f"YAML section {section!r} must be a mapping")
        section_data[key] = value
    with file_path.open("w", encoding="utf-8") as stream:
        yaml_editor.dump(data, stream)


# Architecture: Apply one configuration edit and persist the YAML file.

def edit_yaml(path: str | Path, key: str, value: Any) -> None:
    add_to_yaml(path, None, key, value)


# Architecture: Copy selected configuration or artifact content between directories.

def copy_folder_content(source: str | Path, destination: str | Path) -> None:
    source_path = Path(source)
    destination_path = Path(destination)
    destination_path.mkdir(parents=True, exist_ok=True)
    if source_path.is_file():
        shutil.copy2(source_path, destination_path / source_path.name)
        return
    for child in source_path.iterdir():
        target = destination_path / child.name
        if child.is_dir():
            copy_folder_content(child, target)
        else:
            shutil.copy2(child, target)


# Architecture: Run a helper while hiding legacy console output.

def suppress_printing(function: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
        io.StringIO()
    ):
        return function(*args, **kwargs)


# Architecture: Run a helper with standard output redirected from the caller.

def suppress_stdout(function: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    with contextlib.redirect_stdout(io.StringIO()):
        return function(*args, **kwargs)
