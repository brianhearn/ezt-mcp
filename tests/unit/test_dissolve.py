from __future__ import annotations

import pytest
from shapely.geometry import GeometryCollection, Polygon, shape

from tests.fixtures.synthetic_geometry import grid_square_geometries, square

from ezt_mcp.territory.dissolve import (
    DissolveOptions,
    DissolveValidationError,
    ShapelyGeometryDissolveBackend,
    dissolve_hierarchy_geometries,
)
from ezt_mcp.territory.hierarchy import materialize_assignment_tree


def test_dissolves_flat_leaf_territories_from_synthetic_squares():
    hierarchy = materialize_assignment_tree(
        [
            {"part_id": "A", "territory_path": ["West"]},
            {"part_id": "B", "territory_path": ["West"]},
            {"part_id": "C", "territory_path": ["East"]},
        ],
        tal_id="tal-fixture",
    )

    dissolved = dissolve_hierarchy_geometries(
        hierarchy,
        {
            "A": square(0, 0),
            "B": square(1, 0),
            "C": square(4, 0),
        },
    )

    by_label = {territory.label: territory for territory in dissolved.territories}
    assert len(dissolved.leaf_territories) == 2
    assert len(dissolved.rollup_territories) == 0
    assert by_label["West"].part_ids == ("A", "B")
    assert by_label["West"].geometry.area == pytest.approx(2.0)
    assert by_label["West"].bbox == (0.0, 0.0, 2.0, 1.0)
    assert by_label["East"].geometry.area == pytest.approx(1.0)


def test_dissolves_hierarchical_rollups_bottom_up():
    hierarchy = materialize_assignment_tree(
        [
            {"part_id": "NW1", "territory_path": ["West", "Northwest"]},
            {"part_id": "SW1", "territory_path": ["West", "Southwest"]},
            {"part_id": "NE1", "territory_path": ["East", "Northeast"]},
        ],
        tal_id="tal-hierarchy",
    )

    dissolved = dissolve_hierarchy_geometries(
        hierarchy,
        {
            "NW1": square(0, 1),
            "SW1": square(0, 0),
            "NE1": square(4, 1),
        },
    )

    by_path_id = {territory.territory_id: territory for territory in dissolved.territories}
    west = by_path_id["tal-hierarchy-west"]
    east = by_path_id["tal-hierarchy-east"]

    assert len(dissolved.leaf_territories) == 3
    assert len(dissolved.rollup_territories) == 2
    assert west.is_leaf is False
    assert west.part_ids == ()
    assert west.geometry.area == pytest.approx(2.0)
    assert west.bbox == (0.0, 0.0, 1.0, 2.0)
    assert east.geometry.area == pytest.approx(1.0)

    feature_collection = dissolved.to_feature_collection()
    assert feature_collection["type"] == "FeatureCollection"
    assert feature_collection["properties"]["territory_count"] == 5
    assert feature_collection["properties"]["geometry_backend"] == "shapely"


def test_accepts_geojson_geometry_mappings_and_exports_features():
    hierarchy = materialize_assignment_tree(
        [{"part_id": "A", "territory_path": ["Only"]}],
        tal_id="tal-geojson",
    )

    dissolved = dissolve_hierarchy_geometries(hierarchy, {"A": square(0, 0).__geo_interface__})
    feature = dissolved.territories[0].to_geojson_feature()

    assert feature["type"] == "Feature"
    assert feature["properties"]["territory_id"] == "tal-geojson-only"
    assert shape(feature["geometry"]).area == pytest.approx(1.0)


def test_rejects_missing_part_geometry_before_dissolve():
    hierarchy = materialize_assignment_tree(
        [
            {"part_id": "A", "territory_path": ["Only"]},
            {"part_id": "B", "territory_path": ["Only"]},
        ],
        tal_id="tal-missing",
    )

    with pytest.raises(DissolveValidationError) as exc:
        dissolve_hierarchy_geometries(hierarchy, {"A": square(0, 0)})

    assert exc.value.code == "UNKNOWN_PART_ID"
    assert exc.value.details["missing_part_ids"] == ["B"]


def test_repairs_invalid_bowtie_polygon_to_polygonal_output():
    hierarchy = materialize_assignment_tree(
        [{"part_id": "BAD", "territory_path": ["Repaired"]}],
        tal_id="tal-repair",
    )
    bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    assert not bowtie.is_valid

    dissolved = dissolve_hierarchy_geometries(hierarchy, {"BAD": bowtie})

    assert dissolved.territories[0].geometry.is_valid
    assert dissolved.territories[0].geometry.area > 0


def test_backend_trusts_pre_normalized_geometry_inputs():
    class ExplodingPolygon(Polygon):
        @property
        def is_valid(self):  # type: ignore[override]
            raise AssertionError("backend should not re-check validity for normalized inputs")

    backend = ShapelyGeometryDissolveBackend()
    dissolved = backend.union(
        [ExplodingPolygon(square(0, 0).exterior.coords)],
        operation="leaf",
        context={"territory_id": "tal-fast-path-only"},
    )

    assert dissolved.area == pytest.approx(1.0)


def test_backend_rejects_empty_geometry_batch():
    backend = ShapelyGeometryDissolveBackend()

    with pytest.raises(DissolveValidationError) as exc:
        backend.union(
            [GeometryCollection()],
            operation="leaf",
            context={"territory_id": "tal-empty"},
        )

    assert exc.value.code == "EMPTY_GEOMETRY"
    assert exc.value.details == {"territory_id": "tal-empty"}


def test_partitioned_backend_preserves_dissolved_output():
    backend = ShapelyGeometryDissolveBackend(
        partition_threshold=2,
        target_parts_per_cluster=2,
        max_clusters=10,
    )

    dissolved = backend.union(
        [square(x, 0) for x in range(6)],
        operation="leaf",
        context={"territory_id": "tal-partitioned"},
    )

    assert dissolved.area == pytest.approx(6.0)
    assert dissolved.bounds == pytest.approx((0.0, 0.0, 6.0, 1.0))


def test_dissolve_options_control_simplification_and_partitioning():
    hierarchy = materialize_assignment_tree(
        [{"part_id": f"P{x}", "territory_path": ["Only"]} for x in range(6)],
        tal_id="tal-options",
    )

    dissolved = dissolve_hierarchy_geometries(
        hierarchy,
        {f"P{x}": square(x, 0) for x in range(6)},
        options=DissolveOptions(
            simplify_tolerance=0.0,
            overview_simplify_tolerance=0.5,
            partition_threshold=2,
            target_parts_per_cluster=2,
            max_clusters=10,
        ),
    )

    territory = dissolved.territories[0]
    assert territory.geometry.area == pytest.approx(6.0)
    assert territory.geometry_simple.area == pytest.approx(6.0)
    assert len(territory.geometry_simple.geoms[0].exterior.coords) <= len(
        territory.geometry.geoms[0].exterior.coords
    )


def test_dissolved_hierarchy_exports_geometry_summary_bbox():
    hierarchy = materialize_assignment_tree(
        [
            {"part_id": "A", "territory_path": ["West"]},
            {"part_id": "B", "territory_path": ["East"]},
        ],
        tal_id="tal-summary",
    )

    dissolved = dissolve_hierarchy_geometries(
        hierarchy,
        grid_square_geometries(["A", "B"], columns=2, as_geojson=True),
    )

    assert dissolved.bbox == (0.0, 0.0, 2.0, 1.0)
    assert dissolved.summary() == {
        "geometry_backend": "shapely",
        "territory_count": 2,
        "leaf_territory_count": 2,
        "rollup_territory_count": 0,
        "bbox": [0.0, 0.0, 2.0, 1.0],
    }
