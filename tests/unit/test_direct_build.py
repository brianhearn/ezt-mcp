from __future__ import annotations

import re

from shapely.geometry import shape

from tests.fixtures.synthetic_geometry import square

from ezt_mcp.tools.direct_build import build_direct_tal


def test_direct_build_appends_flat_tal_to_existing_ts():
    request = {
        "ts": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"layer_type": "point", "id": "acct-1"},
                    "geometry": {"type": "Point", "coordinates": [-84.28, 30.44]},
                }
            ],
            "properties": {
                "ts_identity": {
                    "ts_id": "ts-existing",
                    "revision": 4,
                    "content_hash": "sha256:" + "0" * 64,
                    "updated_at": "2026-05-12T19:40:00Z",
                }
            },
        },
        "part_layer": "us_zips",
        "tal_label": "Florida Sales Territories",
        "assignments": [
            {"part_id": "32003", "territory_path": ["North Florida"]},
            {"part_id": "33101", "territory_path": ["South Florida"]},
        ],
    }

    response = build_direct_tal(
        request,
        {
            "32003": square(0, 0),
            "33101": square(3, 0),
        },
    )

    assert response["ok"] is True
    result = response["result"]
    ts = result["ts"]
    assert result["tal_id"] == "tal-florida-sales-territories"
    assert result["territory_count"] == 2
    assert result["hierarchy_summary"] == {
        "max_depth": 0,
        "leaf_territory_count": 2,
        "rollup_territory_count": 0,
    }
    assert result["assignment_summary"]["assigned_part_count"] == 2
    assert result["geometry_summary"] == {
        "geometry_backend": "shapely",
        "territory_count": 2,
        "leaf_territory_count": 2,
        "rollup_territory_count": 0,
        "bbox": [0.0, 0.0, 4.0, 1.0],
    }
    assert result["ts_identity"]["ts_id"] == "ts-existing"
    assert result["ts_identity"]["revision"] == 5
    assert re.fullmatch(r"sha256:[a-f0-9]{64}", result["ts_identity"]["content_hash"])

    assert len(ts["features"]) == 3  # existing point + two territories
    assert ts["properties"]["active_tal_id"] == "tal-florida-sales-territories"
    assert ts["properties"]["territory_alignment_layers"] == [
        {
            "tal_id": "tal-florida-sales-territories",
            "label": "Florida Sales Territories",
            "part_layer": "us_zips",
            "max_depth": 0,
            "territory_count": 2,
            "geometry_backend": "shapely",
            "bbox": [0.0, 0.0, 4.0, 1.0],
            "updated_at": result["ts_identity"]["updated_at"],
        }
    ]

    territory_features = [
        feature
        for feature in ts["features"]
        if feature["properties"].get("tal_id") == "tal-florida-sales-territories"
    ]
    assert {feature["properties"]["label"] for feature in territory_features} == {
        "North Florida",
        "South Florida",
    }
    assert all(feature["properties"]["is_leaf"] for feature in territory_features)
    assert shape(territory_features[0]["geometry"]).is_valid


def test_direct_build_honors_requested_tal_id_when_available():
    request = {
        "part_layer": "us_zips",
        "tal_label": "Florida Sales Territories",
        "tal_id": "tal-custom-fl-sales",
        "assignments": [
            {"part_id": "32003", "territory_path": ["North Florida"]},
        ],
    }

    response = build_direct_tal(request, {"32003": square(0, 0)})

    result = response["result"]
    ts = result["ts"]
    assert result["tal_id"] == "tal-custom-fl-sales"
    assert ts["properties"]["active_tal_id"] == "tal-custom-fl-sales"
    assert ts["properties"]["territory_alignment_layers"][0]["tal_id"] == "tal-custom-fl-sales"
    assert ts["features"][0]["properties"]["tal_id"] == "tal-custom-fl-sales"


def test_direct_build_rejects_requested_tal_id_collision():
    request = {
        "ts": {
            "type": "FeatureCollection",
            "features": [],
            "properties": {
                "territory_alignment_layers": [
                    {"tal_id": "tal-existing", "label": "Existing", "part_layer": "us_zips"}
                ]
            },
        },
        "part_layer": "us_zips",
        "tal_label": "Florida Sales Territories",
        "tal_id": "tal-existing",
        "assignments": [
            {"part_id": "32003", "territory_path": ["North Florida"]},
        ],
    }

    try:
        build_direct_tal(request, {"32003": square(0, 0)})
    except ValueError as exc:
        assert "tal_id already exists" in str(exc)
    else:
        raise AssertionError("Expected requested tal_id collision to be rejected")


def test_direct_build_rejects_invalid_requested_tal_id():
    request = {
        "part_layer": "us_zips",
        "tal_label": "Florida Sales Territories",
        "tal_id": "tal bad/id",
        "assignments": [
            {"part_id": "32003", "territory_path": ["North Florida"]},
        ],
    }

    try:
        build_direct_tal(request, {"32003": square(0, 0)})
    except ValueError as exc:
        assert "tal_id may contain only" in str(exc)
    else:
        raise AssertionError("Expected invalid requested tal_id to be rejected")


def test_direct_build_creates_rollup_tal_and_warning():
    request = {
        "part_layer": "us_zips",
        "tal_label": "US Sales Hierarchy",
        "assignments": [
            {"part_id": "NW1", "territory_path": ["West", "Northwest"]},
            {"part_id": "SW1", "territory_path": ["West", "Southwest"]},
            {"part_id": "NE1", "territory_path": ["East", "Northeast"]},
        ],
    }

    response = build_direct_tal(
        request,
        {
            "NW1": square(0, 1),
            "SW1": square(0, 0),
            "NE1": square(4, 1),
        },
    )

    assert response["result"]["hierarchy_summary"] == {
        "max_depth": 1,
        "leaf_territory_count": 3,
        "rollup_territory_count": 2,
    }
    assert response["result"]["geometry_summary"] == {
        "geometry_backend": "shapely",
        "territory_count": 5,
        "leaf_territory_count": 3,
        "rollup_territory_count": 2,
        "bbox": [0.0, 0.0, 5.0, 2.0],
    }
    assert response["warnings"] == [
        {
            "code": "ROLLUP_TERRITORIES_CREATED",
            "message": "Created hierarchy rollup territories from territory_path values.",
        }
    ]

    features = response["result"]["ts"]["features"]
    by_id = {feature["properties"]["territory_id"]: feature for feature in features}
    west = by_id["tal-us-sales-hierarchy-west"]
    assert west["properties"]["is_leaf"] is False
    assert west["properties"]["part_ids"] == []
    assert shape(west["geometry"]).area == 2.0
    assert by_id["tal-us-sales-hierarchy-west-northwest"]["properties"][
        "parent_territory_id"
    ] == "tal-us-sales-hierarchy-west"
