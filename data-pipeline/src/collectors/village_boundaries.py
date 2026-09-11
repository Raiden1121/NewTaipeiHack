"""Download the official NLSC village-boundary SHP package."""

from __future__ import annotations

import hashlib
import io
import re
import ssl
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .contracts import CollectedPayload, SourceArtifact


VILLAGE_BOUNDARIES_URL = "https://maps.nlsc.gov.tw/download/村(里)界(TWD97_121分帶).zip"
REQUEST_TIMEOUT_SECONDS = 120
MAX_ZIP_BYTES = 250 * 1024 * 1024
OpenURL = Callable[..., Any]


class VillageBoundaryCollectorError(RuntimeError):
    """Raised when the official village-boundary package is unavailable."""


def _open_url(url_or_request: str | Request, *, timeout: int = REQUEST_TIMEOUT_SECONDS) -> Any:
    request = url_or_request
    if isinstance(url_or_request, str):
        request = Request(
            url_or_request,
            headers={"Accept": "application/zip,application/octet-stream", "User-Agent": "NewTaipeiHack-data-pipeline/1.0"},
        )
    context = ssl.create_default_context()
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", None)
    if strict_flag is not None:
        context.verify_flags &= ~strict_flag
    return urlopen(request, timeout=timeout, context=context)


def fetch_village_boundaries(
    *,
    source_url: str = VILLAGE_BOUNDARIES_URL,
    open_url: OpenURL = _open_url,
) -> CollectedPayload:
    """Download and parse the SHP package while retaining the full ZIP artifact."""

    content = _request_bytes(source_url, open_url=open_url)
    artifact = SourceArtifact(
        filename=f"village_boundaries_{hashlib.sha256(content).hexdigest()[:12]}.zip",
        content=content,
        media_type="application/zip",
        sha256="sha256:" + hashlib.sha256(content).hexdigest(),
    )
    try:
        records, members = _parse_shapefile(content)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise VillageBoundaryCollectorError(f"NLSC village-boundary ZIP cannot be parsed: {exc}") from exc
    if not records:
        raise VillageBoundaryCollectorError("NLSC village-boundary ZIP contains no SHP records")
    return CollectedPayload(
        records=records,
        metadata={
            "source_url": source_url,
            "source_crs": "EPSG:3826",
            "format": "ESRI Shapefile",
            "zip_members": members,
            "record_count": len(records),
        },
        artifacts=(artifact,),
    )


def _request_bytes(url: str, *, open_url: OpenURL) -> bytes:
    request_url = _encode_request_url(url)
    request = Request(request_url, headers={"Accept": "application/zip,application/octet-stream", "User-Agent": "NewTaipeiHack-data-pipeline/1.0"})
    try:
        response = open_url(request, timeout=REQUEST_TIMEOUT_SECONDS)
        try:
            content = response.read(MAX_ZIP_BYTES + 1)
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise VillageBoundaryCollectorError(f"NLSC village-boundary request failed: {exc}") from exc
    if len(content) > MAX_ZIP_BYTES:
        raise VillageBoundaryCollectorError("NLSC village-boundary ZIP exceeds size limit")
    if not content:
        raise VillageBoundaryCollectorError("NLSC village-boundary response is empty")
    return content


def _encode_request_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            quote(parts.path, safe="/():,._-"),
            parts.query,
            parts.fragment,
        )
    )


def _parse_shapefile(content: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    import shapefile  # type: ignore

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.namelist()
            for member in members:
                if member.endswith("/"):
                    continue
                target = (root / member).resolve()
                if not str(target).startswith(str(root.resolve()) + "/"):
                    raise ValueError(f"unsafe ZIP member: {member}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(member))
            shp_paths = [root / member for member in members if member.lower().endswith(".shp")]
            if not shp_paths:
                raise ValueError("ZIP has no .shp member")
            shp_path = shp_paths[0]
        reader = shapefile.Reader(str(shp_path), encoding="utf-8", encodingErrors="replace")
        field_names = [field[0] for field in reader.fields[1:]]
        records: list[dict[str, Any]] = []
        for shape_record in reader.iterShapeRecords():
            properties = {
                field: _json_value(value)
                for field, value in zip(field_names, shape_record.record, strict=True)
            }
            geometry = shape_record.shape.__geo_interface__
            records.append({"properties": properties, "geometry": geometry})
        return records, [member for member in members if not member.endswith("/")]


def _json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


__all__ = ["VILLAGE_BOUNDARIES_URL", "VillageBoundaryCollectorError", "fetch_village_boundaries"]
