"""Part-layer discovery resources.

These helpers back the public MCP resources:

- ``ezt://part-layers``
- ``ezt://part-layers/{part_layer}``

The code deliberately separates safe public metadata from internal database metadata
such as ``geo.part_layers.table_name``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


DEFAULT_CAPABILITIES: dict[str, bool] = {
    "direct_build": True,
    "account_build": True,
    "auto_build": True,
    "realign": True,
    "analyze": True,
    "map_selection": True,
}

PUBLIC_LAYER_FIELDS = {
    "part_layer",
    "label",
    "description",
    "country_codes",
    "admin_levels",
    "geometry_type",
    "srid",
    "part_count",
    "id_format",
    "example_part_ids",
    "capabilities",
    "data_version",
    "updated_at",
    "warnings",
}

DETAIL_ONLY_FIELDS = {
    "bbox",
    "supported_admin1",
    "aliases",
    "source_name",
    "source_vintage",
    "id_format_notes",
}

FORBIDDEN_PUBLIC_FIELDS = {
    "table_name",
    "id_field",
    "sql",
    "database_url",
    "host",
    "hostname",
    "storage_url",
    "credential",
    "password",
    "secret",
    "internal_index",
    "internal_function",
}


class UnknownPartLayerError(LookupError):
    """Raised when a part layer does not exist or is unavailable."""

    def __init__(self, part_layer: str):
        super().__init__(f"Unknown part layer: {part_layer}")
        self.part_layer = part_layer
        self.code = "UNKNOWN_PART_LAYER"


@dataclass(frozen=True)
class PartLayerMetadata:
    """Safe public metadata for one canonical part layer."""

    part_layer: str
    label: str
    description: str | None = None
    country_codes: list[str] = field(default_factory=list)
    admin_levels: list[str] = field(default_factory=list)
    geometry_type: str = "MultiPolygon"
    srid: int = 4326
    part_count: int | None = None
    id_format: str | None = None
    example_part_ids: list[str] = field(default_factory=list)
    capabilities: dict[str, bool] = field(default_factory=lambda: DEFAULT_CAPABILITIES.copy())
    data_version: str | None = None
    updated_at: datetime | str | None = None
    warnings: list[str] = field(default_factory=list)
    # Detail resource extras.
    bbox: list[float] | None = None
    supported_admin1: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    source_name: str | None = None
    source_vintage: str | None = None
    id_format_notes: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "PartLayerMetadata":
        """Build metadata from a DB row-like mapping.

        Internal columns may be present in ``record``; they are intentionally not
        represented in the dataclass and therefore cannot leak to resource output.
        """
        capabilities = record.get("capabilities") or DEFAULT_CAPABILITIES.copy()
        if not isinstance(capabilities, dict):
            capabilities = DEFAULT_CAPABILITIES.copy()

        return cls(
            part_layer=str(record["part_layer"]),
            label=str(record["label"]),
            description=record.get("description"),
            country_codes=list(record.get("country_codes") or []),
            admin_levels=list(record.get("admin_levels") or []),
            geometry_type=str(record.get("geometry_type") or "MultiPolygon"),
            srid=int(record.get("srid") or 4326),
            part_count=record.get("part_count"),
            id_format=record.get("id_format"),
            example_part_ids=list(record.get("example_part_ids") or []),
            capabilities={**DEFAULT_CAPABILITIES, **capabilities},
            data_version=record.get("data_version"),
            updated_at=record.get("updated_at"),
            warnings=list(record.get("warnings") or []),
            bbox=record.get("bbox"),
            supported_admin1=list(record.get("supported_admin1") or []),
            aliases=list(record.get("aliases") or []),
            source_name=record.get("source_name"),
            source_vintage=record.get("source_vintage"),
            id_format_notes=record.get("id_format_notes"),
        )

    def to_summary(self) -> dict[str, Any]:
        """Return the list-resource representation."""
        return _drop_empty(
            {
                "part_layer": self.part_layer,
                "label": self.label,
                "description": self.description,
                "country_codes": self.country_codes,
                "admin_levels": self.admin_levels,
                "geometry_type": self.geometry_type,
                "srid": self.srid,
                "part_count": self.part_count,
                "id_format": self.id_format,
                "example_part_ids": self.example_part_ids,
                "capabilities": self.capabilities,
                "data_version": self.data_version,
                "updated_at": _format_datetime(self.updated_at),
                "warnings": self.warnings,
            }
        )

    def to_detail(self) -> dict[str, Any]:
        """Return the detail-resource representation."""
        detail = self.to_summary()
        detail.update(
            _drop_empty(
                {
                    "bbox": self.bbox,
                    "supported_admin1": self.supported_admin1,
                    "aliases": self.aliases,
                    "source_name": self.source_name,
                    "source_vintage": self.source_vintage,
                    "id_format_notes": self.id_format_notes,
                }
            )
        )
        return detail


class PartLayerRepository(Protocol):
    """Repository protocol used by resource handlers."""

    async def list_active_part_layers(self) -> list[PartLayerMetadata]: ...

    async def get_part_layer(self, part_layer: str) -> PartLayerMetadata | None: ...


async def list_part_layers_resource(repo: PartLayerRepository) -> dict[str, Any]:
    """Return the public ``ezt://part-layers`` payload."""
    layers = [layer.to_summary() for layer in await repo.list_active_part_layers()]
    return {
        "resource": "ezt://part-layers",
        "generated_at": _format_datetime(datetime.now(timezone.utc)),
        "layers": layers,
        "layer_count": len(layers),
    }


async def get_part_layer_resource(repo: PartLayerRepository, part_layer: str) -> dict[str, Any]:
    """Return the public ``ezt://part-layers/{part_layer}`` payload."""
    layer = await repo.get_part_layer(part_layer)
    if layer is None:
        raise UnknownPartLayerError(part_layer)
    return {
        "resource": f"ezt://part-layers/{part_layer}",
        "generated_at": _format_datetime(datetime.now(timezone.utc)),
        "layer": layer.to_detail(),
    }


def assert_no_forbidden_public_fields(payload: dict[str, Any]) -> None:
    """Guardrail used by tests and optionally by runtime assertions."""
    leaked = sorted(_find_forbidden_keys(payload))
    if leaked:
        raise AssertionError(f"Forbidden public field(s) leaked: {', '.join(leaked)}")


def _find_forbidden_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if lowered in FORBIDDEN_PUBLIC_FIELDS:
                found.add(str(key))
            found.update(_find_forbidden_keys(child))
    elif isinstance(value, list):
        for item in value:
            found.update(_find_forbidden_keys(item))
    return found


def _drop_empty(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if value is not None and value != [] and value != {}
    }


def _format_datetime(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
