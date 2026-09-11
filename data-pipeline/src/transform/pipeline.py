"""Static dataset dispatch for raw-to-curated transforms."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

from analytics.config import load_topic_rules

from .contracts import TransformResult
from .budget import transform_youth_budgets
from .childcare import transform_babysitting_places
from .elections import transform_elections
from .education import transform_college_majors, transform_graduate_majors
from .geography import DistrictResolver
from .housing import transform_house_prices, transform_rentals
from .labor import transform_job_vacancies, transform_job_vacancy_salaries, transform_wages
from .life_events import transform_births, transform_marriages
from .mobility import transform_movement
from .population import transform_population
from .population_villages import transform_population_villages
from .training import transform_talent_demand, transform_training_numbers, transform_vt_courses
from .transport import transform_bike_stops, transform_bus_stops, transform_railway_stops
from .join_proposals import transform_join_proposals
from .youth_council_minutes import transform_youth_council_minutes
from .service_points import (
    load_youth_service_point_location_reference,
    transform_youth_service_points,
)
from .village_boundaries import transform_village_boundaries


class UnsupportedDatasetError(ValueError):
    """The requested dataset is not present in the static transform registry."""


_ALIASES = {
    "moving_in": "movement",
    "birth_nums": "births",
    "marriage_nums": "marriages",
    "house_price": "house_prices",
    "rental_price": "rentals",
    "job_vacancy": "job_vacancies",
    "job_vacancy_salary": "job_vacancy_salaries",
    "wage": "wages",
    "college_major": "college_majors",
    "graduate_major": "graduate_majors",
    "vt_course": "vt_courses",
    "training_nums": "training_numbers",
    "talent_demand": "talent_demand",
    "bus_stop": "bus_stops",
    "railway_stop": "railway_stops",
    "bike_stop": "bike_stops",
    "babysitting_place": "babysitting_places",
    "Babysitting_place": "babysitting_places",
}
_GEOGRAPHIC_TRANSFORMS = {
    "population": transform_population,
    "population_villages": transform_population_villages,
    "movement": transform_movement,
    "births": transform_births,
    "marriages": transform_marriages,
    "house_prices": transform_house_prices,
    "rentals": transform_rentals,
    "job_vacancies": transform_job_vacancies,
    "job_vacancy_salaries": transform_job_vacancy_salaries,
    "vt_courses": transform_vt_courses,
    "bus_stops": transform_bus_stops,
    "railway_stops": transform_railway_stops,
    "bike_stops": transform_bike_stops,
    "babysitting_places": transform_babysitting_places,
    "elections": transform_elections,
    "youth_service_points": transform_youth_service_points,
}
_PLAIN_TRANSFORMS = {
    "graduate_majors": transform_graduate_majors,
    "training_numbers": transform_training_numbers,
    "talent_demand": transform_talent_demand,
    "wages": transform_wages,
    "youth_budgets": transform_youth_budgets,
    "village_boundaries": transform_village_boundaries,
}
_TOPIC_TRANSFORMS = {
    "join_proposals": transform_join_proposals,
    "youth_council_minutes": transform_youth_council_minutes,
}


def run_transform(
    dataset: str,
    records: Iterable[Mapping[str, Any]] | Mapping[str, Any],
    *,
    resolver: DistrictResolver | None = None,
    fetched_at: str | None = None,
    config_dir: str | Path | None = None,
) -> TransformResult:
    """Run one explicitly registered transform without live data access."""

    canonical_dataset = canonicalize_dataset(dataset)
    if canonical_dataset == "college_majors":
        if not isinstance(records, Mapping):
            raise TypeError("college_majors requires overview_records/detail_records envelope")
        school_locations = (
            _record_list(records.get("school_locations"), field="school_locations")
            if "school_locations" in records
            else None
        )
        active_resolver = resolver
        if school_locations is not None and active_resolver is None:
            active_resolver = _default_resolver()
        return transform_college_majors(
            _record_list(records.get("overview_records"), field="overview_records"),
            _record_list(records.get("detail_records", []), field="detail_records"),
            resolver=active_resolver,
            school_locations=school_locations,
            fetched_at=fetched_at,
        )
    if canonical_dataset == "wages" and isinstance(records, Mapping):
        metadata = records.get("metadata")
        envelope_fetched_at = metadata.get("fetched_at") if isinstance(metadata, Mapping) else None
        records = _record_list(records.get("records"), field="records")
        fetched_at = fetched_at or envelope_fetched_at
    if canonical_dataset == "youth_service_points":
        active_resolver = resolver or _default_resolver()
        reference_dir = Path(config_dir) if config_dir is not None else _default_config_dir()
        location_reference = load_youth_service_point_location_reference(
            reference_dir / "reference" / "youth_service_points_locations.json"
        )
        return transform_youth_service_points(
            _record_list(records, field="records"),
            resolver=active_resolver,
            fetched_at=fetched_at,
            location_reference=location_reference,
        )
    if canonical_dataset in _GEOGRAPHIC_TRANSFORMS:
        active_resolver = resolver or _default_resolver()
        return _GEOGRAPHIC_TRANSFORMS[canonical_dataset](
            _record_list(records, field="records"),
            resolver=active_resolver,
            fetched_at=fetched_at,
        )
    if canonical_dataset in _PLAIN_TRANSFORMS or canonical_dataset in _TOPIC_TRANSFORMS:
        if isinstance(records, Mapping):
            metadata = records.get("metadata")
            envelope_fetched_at = (
                metadata.get("fetched_at")
                if isinstance(metadata, Mapping)
                else records.get("fetched_at")
            )
            records = _record_list(records.get("records"), field="records")
            fetched_at = fetched_at or envelope_fetched_at
        if canonical_dataset in _TOPIC_TRANSFORMS:
            rules_path = Path(config_dir) if config_dir is not None else _default_config_dir()
            rules = load_topic_rules(rules_path / "youth_topic_rules.json")
            return _TOPIC_TRANSFORMS[canonical_dataset](
                _record_list(records, field="records"),
                fetched_at=fetched_at,
                rules=rules,
            )
        return _PLAIN_TRANSFORMS[canonical_dataset](
            _record_list(records, field="records"),
            fetched_at=fetched_at,
        )
    raise AssertionError(f"dataset registry missing transform for {canonical_dataset}")


def canonicalize_dataset(dataset: str) -> str:
    canonical = _ALIASES.get(dataset, dataset)
    supported = {"college_majors", *_GEOGRAPHIC_TRANSFORMS, *_PLAIN_TRANSFORMS, *_TOPIC_TRANSFORMS}
    if canonical not in supported:
        raise UnsupportedDatasetError(
            f"unsupported dataset {dataset!r}; supported datasets: {', '.join(sorted(supported))}"
        )
    return canonical


def dataset_requires_resolver(dataset: str) -> bool:
    return canonicalize_dataset(dataset) in _GEOGRAPHIC_TRANSFORMS


@lru_cache(maxsize=1)
def _default_resolver() -> DistrictResolver:
    config_path = Path(__file__).resolve().parents[2] / "config" / "districts.json"
    return DistrictResolver.from_json(config_path)


def _default_config_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "config"


def _record_list(value: Any, *, field: str) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping) or isinstance(value, (str, bytes)) or value is None:
        raise TypeError(f"{field} must be an array of JSON objects")
    rows = list(value)
    if any(not isinstance(row, Mapping) for row in rows):
        raise TypeError(f"{field} must contain only JSON objects")
    return rows
