from __future__ import annotations

import pytest

from ezt_mcp.territory.hierarchy import HierarchyValidationError, materialize_assignment_tree


def test_materializes_flat_assignment_tree():
    hierarchy = materialize_assignment_tree(
        [
            {"part_id": "32003", "territory_path": ["North Florida"]},
            {"part_id": "33101", "territory_path": ["South Florida"]},
            {"part_id": "33602", "territory_path": ["Central Florida"]},
        ],
        tal_id="tal-fl-sales",
    )

    assert hierarchy.summary() == {
        "max_depth": 0,
        "leaf_territory_count": 3,
        "rollup_territory_count": 0,
    }
    assert [node.parent_territory_id for node in hierarchy.nodes] == [None, None, None]
    assert {node.label for node in hierarchy.leaf_nodes} == {
        "North Florida",
        "South Florida",
        "Central Florida",
    }
    assert all(node.is_leaf for node in hierarchy.nodes)


def test_materializes_hierarchical_rollups_and_leaf_nodes():
    hierarchy = materialize_assignment_tree(
        [
            {"part_id": "33101", "territory_path": ["East", "Southeast", "South Florida"]},
            {"part_id": "33602", "territory_path": ["East", "Southeast", "Central Florida"]},
            {"part_id": "10001", "territory_path": ["East", "Northeast", "New York Metro"]},
            {"part_id": "94105", "territory_path": ["West", "Pacific", "Bay Area"]},
        ],
        tal_id="tal-us-sales-hierarchy",
    )

    assert hierarchy.summary() == {
        "max_depth": 2,
        "leaf_territory_count": 4,
        "rollup_territory_count": 5,
    }
    by_path = {node.path: node for node in hierarchy.nodes}
    assert by_path[("East",)].is_leaf is False
    assert by_path[("East", "Southeast")].parent_territory_id == by_path[("East",)].territory_id
    assert by_path[("East", "Southeast", "South Florida")].part_ids == ["33101"]
    assert by_path[("East", "Southeast", "South Florida")].depth == 2
    assert by_path[("East", "Southeast", "South Florida")].parent_territory_id == by_path[
        ("East", "Southeast")
    ].territory_id


def test_rejects_mixed_leaf_and_rollup_node():
    with pytest.raises(HierarchyValidationError) as exc:
        materialize_assignment_tree(
            [
                {"part_id": "10001", "territory_path": ["East"]},
                {"part_id": "33101", "territory_path": ["East", "Southeast"]},
            ],
            tal_id="tal-mixed",
        )

    assert exc.value.code == "CLARIFICATION_REQUIRED"
    assert exc.value.details["existing_leaf_path"] == ["East"]


def test_rejects_assigning_parts_to_existing_rollup_node():
    with pytest.raises(HierarchyValidationError) as exc:
        materialize_assignment_tree(
            [
                {"part_id": "33101", "territory_path": ["East", "Southeast"]},
                {"part_id": "10001", "territory_path": ["East"]},
            ],
            tal_id="tal-mixed",
        )

    assert exc.value.code == "CLARIFICATION_REQUIRED"
    assert exc.value.details["rollup_path"] == ["East"]


def test_dedupes_duplicate_part_when_leaf_path_matches():
    hierarchy = materialize_assignment_tree(
        [
            {"part_id": "33101", "territory_path": ["South Florida"]},
            {"part_id": "33101", "territory_path": [" South   Florida "]},
        ],
        tal_id="tal-flat",
    )

    assert hierarchy.leaf_nodes[0].part_ids == ["33101"]
    assert len(hierarchy.warnings) == 1
    assert hierarchy.warnings[0].code == "DUPLICATE_PART_ASSIGNMENT_DEDUPED"


def test_rejects_duplicate_part_when_leaf_path_conflicts():
    with pytest.raises(HierarchyValidationError) as exc:
        materialize_assignment_tree(
            [
                {"part_id": "33101", "territory_path": ["South Florida"]},
                {"part_id": "33101", "territory_path": ["Central Florida"]},
            ],
            tal_id="tal-flat",
        )

    assert exc.value.code == "CLARIFICATION_REQUIRED"
    assert exc.value.details["part_id"] == "33101"
    assert exc.value.details["previous_territory_path"] == ["south florida"]
    assert exc.value.details["conflicting_territory_path"] == ["central florida"]


def test_assigns_deterministic_ids_with_collision_suffixes():
    hierarchy = materialize_assignment_tree(
        [
            {"part_id": "1", "territory_path": ["A B"]},
            {"part_id": "2", "territory_path": ["A-B"]},
        ],
        tal_id="TAL Demo",
    )

    assert [node.territory_id for node in hierarchy.nodes] == ["tal-demo-a-b", "tal-demo-a-b-2"]


def test_exports_agent_friendly_territory_properties():
    hierarchy = materialize_assignment_tree(
        [{"part_id": "33101", "territory_path": ["East", "South Florida"]}],
        tal_id="tal-demo",
    )

    properties = hierarchy.territory_properties()
    assert properties == [
        {
            "territory_id": "tal-demo-east",
            "label": "East",
            "tal_id": "tal-demo",
            "depth": 0,
            "parent_territory_id": None,
            "is_leaf": False,
            "part_ids": [],
        },
        {
            "territory_id": "tal-demo-east-south-florida",
            "label": "South Florida",
            "tal_id": "tal-demo",
            "depth": 1,
            "parent_territory_id": "tal-demo-east",
            "is_leaf": True,
            "part_ids": ["33101"],
        },
    ]
