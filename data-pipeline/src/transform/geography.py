"""Canonical New Taipei district lookup and TopoJSON boundary resolution."""

from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from .common import clean_text


DistrictMatch = tuple[str, str]
Point = tuple[float, float]
Polygon = list[list[Point]]


class DistrictResolver:
    def __init__(
        self,
        districts: Iterable[dict[str, Any]],
        *,
        boundaries: dict[str, list[Polygon]] | None = None,
    ) -> None:
        self._districts = [deepcopy(row) for row in districts]
        self._boundaries = boundaries or {}
        self._by_id: dict[str, DistrictMatch] = {}
        self._by_name: dict[str, DistrictMatch] = {}
        self._by_zip: dict[str, DistrictMatch] = {}
        for row in self._districts:
            district_id = str(row["district_id"])
            district_name = str(row["district_name"])
            match = (district_id, district_name)
            if district_id in self._by_id:
                raise ValueError(f"duplicate district ID: {district_id}")
            self._by_id[district_id] = match
            for value in (district_name, *row.get("aliases", [])):
                key = clean_text(value)
                if key:
                    self._by_name[key] = match
            postal_code = clean_text(row.get("postal_code"))
            if postal_code:
                self._by_zip[postal_code] = match

    @classmethod
    def from_json(cls, path: str | Path) -> "DistrictResolver":
        config_path = Path(path)
        with config_path.open(encoding="utf-8") as handle:
            config = json.load(handle)
        districts = config.get("districts")
        if not isinstance(districts, list):
            raise ValueError("district config must contain a districts list")
        boundary_value = config.get("boundary_file")
        boundaries: dict[str, list[Polygon]] = {}
        if boundary_value:
            boundary_path = (config_path.parent / str(boundary_value)).resolve()
            boundaries = _load_topojson_boundaries(boundary_path)
        return cls(districts, boundaries=boundaries)

    @property
    def districts(self) -> list[dict[str, Any]]:
        return deepcopy(self._districts)

    def resolve_name(self, value: Any) -> DistrictMatch | None:
        key = clean_text(value)
        return self._by_name.get(key) if key else None

    def resolve_code(self, value: Any) -> DistrictMatch | None:
        key = clean_text(value)
        if not key:
            return None
        direct = self._by_id.get(key)
        if direct:
            return direct
        matches = {match for district_id, match in self._by_id.items() if key.startswith(district_id)}
        return next(iter(matches)) if len(matches) == 1 else None

    def resolve_zip(self, value: Any) -> DistrictMatch | None:
        key = clean_text(value)
        return self._by_zip.get(key) if key else None

    def resolve_point(self, latitude: float, longitude: float) -> DistrictMatch | None:
        if isinstance(latitude, bool) or isinstance(longitude, bool):
            return None
        try:
            lat = float(latitude)
            lon = float(longitude)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(lat) or not math.isfinite(lon):
            return None
        matches = []
        for district_id, polygons in self._boundaries.items():
            if any(_point_in_polygon((lon, lat), polygon) for polygon in polygons):
                match = self._by_id.get(district_id)
                if match:
                    matches.append(match)
        return matches[0] if len(matches) == 1 else None


def _load_topojson_boundaries(path: Path) -> dict[str, list[Polygon]]:
    with path.open(encoding="utf-8") as handle:
        topology = json.load(handle)
    if topology.get("type") != "Topology":
        raise ValueError("boundary file must be TopoJSON")
    objects = topology.get("objects", {})
    collection = objects.get("map")
    if not isinstance(collection, dict) or collection.get("type") != "GeometryCollection":
        raise ValueError("boundary TopoJSON must contain objects.map")
    decoded_arcs = _decode_arcs(topology)
    boundaries: dict[str, list[Polygon]] = {}
    for geometry in collection.get("geometries", []):
        properties = geometry.get("properties", {})
        district_id = clean_text(properties.get("id"))
        if not district_id:
            continue
        geometry_type = geometry.get("type")
        arcs = geometry.get("arcs", [])
        if geometry_type == "Polygon":
            polygons = [_decode_polygon(arcs, decoded_arcs)]
        elif geometry_type == "MultiPolygon":
            polygons = [_decode_polygon(polygon, decoded_arcs) for polygon in arcs]
        else:
            continue
        boundaries[district_id] = polygons
    return boundaries


def _decode_arcs(topology: dict[str, Any]) -> list[list[Point]]:
    transform = topology.get("transform") or {}
    scale = transform.get("scale", [1, 1])
    translate = transform.get("translate", [0, 0])
    decoded: list[list[Point]] = []
    for arc in topology.get("arcs", []):
        x = 0.0
        y = 0.0
        points: list[Point] = []
        for delta_x, delta_y in arc:
            x += delta_x
            y += delta_y
            points.append((x * scale[0] + translate[0], y * scale[1] + translate[1]))
        decoded.append(points)
    return decoded


def _decode_polygon(rings: list[list[int]], decoded_arcs: list[list[Point]]) -> Polygon:
    return [_stitch_ring(arc_indexes, decoded_arcs) for arc_indexes in rings]


def _stitch_ring(arc_indexes: list[int], decoded_arcs: list[list[Point]]) -> list[Point]:
    ring: list[Point] = []
    for arc_index in arc_indexes:
        points = decoded_arcs[arc_index] if arc_index >= 0 else list(reversed(decoded_arcs[~arc_index]))
        ring.extend(points if not ring else points[1:])
    return ring


def _point_in_polygon(point: Point, polygon: Polygon) -> bool:
    if not polygon or not _point_in_ring(point, polygon[0]):
        return False
    return not any(_point_in_ring(point, hole) for hole in polygon[1:])


def _point_in_ring(point: Point, ring: list[Point]) -> bool:
    if len(ring) < 3:
        return False
    x, y = point
    inside = False
    previous = ring[-1]
    for current in ring:
        x1, y1 = previous
        x2, y2 = current
        if _point_on_segment(point, previous, current):
            return True
        if (y1 > y) != (y2 > y):
            intersection_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < intersection_x:
                inside = not inside
        previous = current
    return inside


def _point_on_segment(point: Point, start: Point, end: Point, epsilon: float = 1e-12) -> bool:
    x, y = point
    x1, y1 = start
    x2, y2 = end
    cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
    if abs(cross) > epsilon:
        return False
    return min(x1, x2) - epsilon <= x <= max(x1, x2) + epsilon and min(y1, y2) - epsilon <= y <= max(y1, y2) + epsilon
