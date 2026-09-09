"""Load and select wall-clock refresh profiles."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path


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


__all__ = [
    "PROFILE_NAMES",
    "SUPPORTED_DATASETS",
    "datasets_for_profile",
    "load_refresh_profiles",
    "validate_refresh_profiles",
]
