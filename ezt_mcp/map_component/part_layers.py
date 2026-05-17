"""Map Component part-layer tile manifest helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class PartLayerTileManifest:
    """Browser-safe metadata for one PMTiles-backed part layer."""

    part_layer: str
    label: str
    url_path: str
    source_layer: str = "parts"
    part_id_property: str = "part_id"
    label_property: str = "part_id"
    default_visible: bool = False
    selectable: bool = True
    minzoom: int = 5
    label_minzoom: int = 7
    bounds: tuple[float, float, float, float] | None = None
    mutually_exclusive_group: str = "part_layer"

    def to_render_payload(self, *, public_base_url: str) -> dict[str, Any]:
        return {
            "part_layer": self.part_layer,
            "label": self.label,
            "url": f"{public_base_url.rstrip('/')}{self.url_path}",
            "source_layer": self.source_layer,
            "part_id_property": self.part_id_property,
            "label_property": self.label_property,
            "default_visible": self.default_visible,
            "selectable": self.selectable,
            "minzoom": self.minzoom,
            "label_minzoom": self.label_minzoom,
            "bounds": list(self.bounds) if self.bounds is not None else None,
            "mutually_exclusive_group": self.mutually_exclusive_group,
        }


PART_LAYER_TILE_MANIFESTS: dict[str, PartLayerTileManifest] = {
    "us_zips": PartLayerTileManifest(
        part_layer="us_zips",
        label="US ZIP Codes",
        url_path="/assets/tiles/parts/us_zips.pmtiles",
        bounds=(-125.0, 24.5, -66.5, 49.5),
    ),
}


def resolve_part_layer_tiles(
    requested: Any,
    *,
    public_base_url: str,
    active_part_layer: Any = None,
    default_part_layer: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Resolve caller/TS requested part layers into render payload metadata.

    The result is session-scoped: it describes only the part layers available for
    this map workflow. Selection remains mutually exclusive through
    ``active_part_layer``.
    """
    requested_ids = _requested_part_layer_ids(requested)
    if not requested_ids and default_part_layer:
        requested_ids = [default_part_layer]

    manifests = [
        PART_LAYER_TILE_MANIFESTS[part_layer]
        for part_layer in requested_ids
        if part_layer in PART_LAYER_TILE_MANIFESTS
    ]
    if not manifests:
        return [], None

    active = str(active_part_layer or "").strip()
    if active not in {manifest.part_layer for manifest in manifests}:
        active = manifests[0].part_layer

    payloads = []
    for manifest in manifests:
        item = manifest.to_render_payload(public_base_url=public_base_url)
        item["default_visible"] = manifest.part_layer == active
        payloads.append(item)
    return payloads, active


def _requested_part_layer_ids(value: Any) -> list[str]:
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else [value]
    result: list[str] = []
    for item in raw_items:
        if isinstance(item, str):
            part_layer = item.strip()
        elif isinstance(item, Mapping):
            part_layer = str(item.get("part_layer") or "").strip()
        else:
            part_layer = ""
        if part_layer and part_layer not in result:
            result.append(part_layer)
    return result
