"""Load and select wall-clock refresh profiles."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import CollectorSpec, ExecutionUnit
from .schedule import build_current_execution_units
from .state import is_refresh_due, refresh_state_key


_DEFAULT_PROFILES_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "refresh_profiles.json"
)


PROFILE_NAMES: tuple[str, ...] = ("daily", "weekly", "monthly")

SUPPORTED_DATASETS: tuple[str, ...] = (
    "population",
    "movement",
    "births",
    "marriages",
    "wages",
    "college_majors",
    "graduate_majors",
    "house_prices",
    "rentals",
    "job_vacancies",
    "job_vacancy_salaries",
    "vt_courses",
    "training_numbers",
    "talent_demand",
    "youth_budgets",
    "bus_stops",
    "railway_stops",
    "bike_stops",
)


def load_refresh_profiles(path: str | Path) -> dict[str, tuple[str, ...]]:
    """Load and validate refresh profiles from a versioned JSON file."""

    profile_path = Path(path)
    try:
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid refresh profile JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("refresh profile document must be a JSON object")
    if payload.get("version") != 1:
        raise ValueError("refresh profile document must contain version 1")

    raw_profiles = payload.get("profiles")
    if not isinstance(raw_profiles, dict):
        raise ValueError("refresh profile document must contain a profiles object")

    unknown_profiles = set(raw_profiles) - set(PROFILE_NAMES)
    if unknown_profiles:
        names = ", ".join(sorted(unknown_profiles))
        raise ValueError(f"unknown refresh profile(s): {names}")

    profiles: dict[str, tuple[str, ...]] = {}
    for profile, datasets in raw_profiles.items():
        if not isinstance(datasets, list):
            raise ValueError(f"profile {profile!r} must contain a list")
        profiles[profile] = tuple(datasets)

    validate_refresh_profiles(profiles, SUPPORTED_DATASETS)
    return profiles


def validate_refresh_profiles(
    profiles: Mapping[str, Sequence[str]], known_datasets: Iterable[str]
) -> None:
    """Validate profile names, dataset names, and cross-profile uniqueness."""

    unknown_profiles = set(profiles) - set(PROFILE_NAMES)
    if unknown_profiles:
        names = ", ".join(sorted(unknown_profiles))
        raise ValueError(f"unknown refresh profile(s): {names}")

    known = set(known_datasets)
    seen: set[str] = set()
    for profile, datasets in profiles.items():
        if not isinstance(datasets, Sequence) or isinstance(datasets, (str, bytes)):
            raise ValueError(f"profile {profile!r} must contain a sequence")
        for dataset in datasets:
            if not isinstance(dataset, str):
                raise ValueError(f"dataset in profile {profile!r} must be a string")
            if dataset not in known:
                raise ValueError(f"unknown dataset in profile {profile!r}: {dataset}")
            if dataset in seen:
                raise ValueError(f"dataset appears in multiple profiles: {dataset}")
            seen.add(dataset)


def datasets_for_profile(
    profiles: Mapping[str, Sequence[str]],
    profile: str,
    selected: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """Return profile datasets in configuration order, optionally filtered."""

    if profile not in PROFILE_NAMES or profile not in profiles:
        raise ValueError(f"unknown refresh profile: {profile}")

    datasets = profiles[profile]
    if not isinstance(datasets, Sequence) or isinstance(datasets, (str, bytes)):
        raise ValueError(f"profile {profile!r} must contain a sequence")

    configured = tuple(datasets)
    if selected is None:
        return configured
    if isinstance(selected, (str, bytes)):
        raise ValueError("selected datasets must be a sequence of dataset names")

    selected_tuple = tuple(selected)
    if len(set(selected_tuple)) != len(selected_tuple):
        raise ValueError("selected datasets must not contain duplicates")
    unknown = set(selected_tuple) - set(configured)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(
            f"selected dataset(s) are not in profile {profile!r}: {names}"
        )
    return tuple(dataset for dataset in configured if dataset in selected_tuple)


def build_refresh_units(
    specs: Iterable[CollectorSpec],
    profile: str,
    *,
    state: Mapping[str, Any] | None = None,
    selected: Sequence[str] | None = None,
    failed_only: bool = False,
    now: datetime | None = None,
    profiles: Mapping[str, Sequence[str]] | None = None,
) -> list[ExecutionUnit]:
    """Build only the current execution units that are due for a profile."""

    configured_profiles = (
        load_refresh_profiles(_DEFAULT_PROFILES_PATH)
        if profiles is None
        else profiles
    )
    validate_refresh_profiles(configured_profiles, SUPPORTED_DATASETS)
    datasets = datasets_for_profile(configured_profiles, profile, selected)
    selected_datasets = set(datasets)
    current = now or datetime.now(timezone.utc)
    current_units = build_current_execution_units(specs, now=current)
    state_units = _state_units(state)

    due_units: list[ExecutionUnit] = []
    for unit in current_units:
        if unit.spec.dataset not in selected_datasets:
            continue
        entry = state_units.get(refresh_state_key(unit))
        if is_refresh_due(
            entry,
            now=current,
            profile=profile,
            failed_only=failed_only,
        ):
            due_units.append(unit)
    return due_units


def _state_units(state: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if state is None:
        return {}
    units = state.get("units", {})
    if not isinstance(units, Mapping):
        raise ValueError("refresh state must contain a units object")
    return units


__all__ = [
    "PROFILE_NAMES",
    "SUPPORTED_DATASETS",
    "build_refresh_units",
    "datasets_for_profile",
    "load_refresh_profiles",
    "validate_refresh_profiles",
]
