from __future__ import annotations

import asyncio

import pytest

from ezt_mcp.resources.part_layers import (
    PartLayerMetadata,
    UnknownPartLayerError,
    assert_no_forbidden_public_fields,
    get_part_layer_resource,
    list_part_layers_resource,
)


class FakePartLayerRepo:
    def __init__(self):
        self.layers = {
            "us_zips": PartLayerMetadata.from_record(
                {
                    "part_layer": "us_zips",
                    "table_name": "geo.us_postal",  # must never leak
                    "id_field": "postal_code",      # must never leak
                    "label": "US ZIP Codes",
                    "description": "United States ZIP Code polygons for territory construction.",
                    "country_codes": ["US"],
                    "admin_levels": ["postal"],
                    "geometry_type": "MultiPolygon",
                    "srid": 4326,
                    "part_count": 33791,
                    "id_format": "5-digit ZIP Code string",
                    "example_part_ids": ["30301", "33101", "94105"],
                    "capabilities": {"direct_build": True},
                    "data_version": "2026-05",
                    "updated_at": "2026-05-01T00:00:00Z",
                    "aliases": ["ZIP", "ZIP Code", "postal code"],
                    "source_name": "EasyTerritory curated geography",
                    "source_vintage": "2026-05",
                }
            ),
            "us_counties": PartLayerMetadata.from_record(
                {
                    "part_layer": "us_counties",
                    "table_name": "geo.us_county",  # must never leak
                    "label": "US Counties",
                    "country_codes": ["US"],
                    "admin_levels": ["county"],
                    "part_count": 3234,
                    "id_format": "County FIPS string",
                    "example_part_ids": ["12073", "13121", "06075"],
                    "updated_at": "2026-05-01T00:00:00Z",
                }
            ),
        }

    async def list_active_part_layers(self):
        return list(self.layers.values())

    async def get_part_layer(self, part_layer: str):
        return self.layers.get(part_layer)


def test_list_part_layers_resource_returns_safe_summaries():
    payload = asyncio.run(list_part_layers_resource(FakePartLayerRepo()))

    assert payload["resource"] == "ezt://part-layers"
    assert payload["layer_count"] == 2
    assert {layer["part_layer"] for layer in payload["layers"]} == {"us_zips", "us_counties"}
    assert_no_forbidden_public_fields(payload)


def test_get_part_layer_resource_returns_detail_metadata():
    payload = asyncio.run(get_part_layer_resource(FakePartLayerRepo(), "us_zips"))

    assert payload["resource"] == "ezt://part-layers/us_zips"
    layer = payload["layer"]
    assert layer["part_layer"] == "us_zips"
    assert layer["aliases"] == ["ZIP", "ZIP Code", "postal code"]
    assert layer["capabilities"]["direct_build"] is True
    assert layer["capabilities"]["auto_build"] is True
    assert_no_forbidden_public_fields(payload)


def test_get_part_layer_resource_unknown_layer():
    with pytest.raises(UnknownPartLayerError) as exc:
        asyncio.run(get_part_layer_resource(FakePartLayerRepo(), "moon_craters"))

    assert exc.value.code == "UNKNOWN_PART_LAYER"
    assert exc.value.part_layer == "moon_craters"
