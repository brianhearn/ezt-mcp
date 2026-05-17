from __future__ import annotations

import pytest

from tests.fixtures.synthetic_geometry import grid_square_geometries

from ezt_mcp.territory.dissolve import dissolve_hierarchy_geometries
from ezt_mcp.territory.hierarchy import materialize_assignment_tree
from ezt_mcp.territory.repair import (
    RepairPolicy,
    RepairSummary,
    RepairValidationError,
    parse_repair_policy,
    repair_dissolved_hierarchy,
)


def test_parse_repair_policy_defaults_and_supported_values():
    assert parse_repair_policy(None) is RepairPolicy.DEFAULT
    assert parse_repair_policy("") is RepairPolicy.DEFAULT
    assert parse_repair_policy("default") is RepairPolicy.DEFAULT
    assert parse_repair_policy("strict") is RepairPolicy.STRICT
    assert parse_repair_policy("report_only") is RepairPolicy.REPORT_ONLY


def test_parse_repair_policy_rejects_unknown_value():
    with pytest.raises(RepairValidationError) as exc:
        parse_repair_policy("aggressive")

    assert exc.value.code == "INVALID_REPAIR_POLICY"
    assert exc.value.details == {
        "repair_policy": "aggressive",
        "allowed_values": ["default", "strict", "report_only"],
    }
    assert exc.value.to_error()["user_action_required"] is True


def test_repair_summary_serializes_public_contract_shape():
    summary = RepairSummary(
        holes_filled=1,
        contiguity_repairs=2,
        changed_part_ids=("P2", "P1"),
    )

    assert summary.to_dict() == {
        "holes_filled": 1,
        "contiguity_repairs": 2,
        "changed_part_ids": ["P2", "P1"],
    }


def test_repair_dissolved_hierarchy_is_noop_skeleton():
    hierarchy = materialize_assignment_tree(
        [
            {"part_id": "A", "territory_path": ["West"]},
            {"part_id": "B", "territory_path": ["East"]},
        ],
        tal_id="tal-repair",
    )
    dissolved = dissolve_hierarchy_geometries(
        hierarchy,
        grid_square_geometries(["A", "B"], columns=2),
    )

    repaired = repair_dissolved_hierarchy(dissolved, policy="report_only")

    assert repaired.policy is RepairPolicy.REPORT_ONLY
    assert repaired.hierarchy is dissolved
    assert repaired.summary.to_dict() == {
        "holes_filled": 0,
        "contiguity_repairs": 0,
        "changed_part_ids": [],
    }
    assert repaired.warnings == ()
