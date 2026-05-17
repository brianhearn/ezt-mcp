"""Territory topology repair policy seam.

The real repair heuristics for holes, gaps, and contiguity will live here.  The
current implementation is intentionally a no-op pipeline with strict policy
parsing so Direct Build has a stable contract before topology-changing behavior
is introduced.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ezt_mcp.territory.dissolve import DissolvedHierarchy

class RepairPolicy(StrEnum):
    """Supported v1 repair policy modes."""

    DEFAULT = "default"
    STRICT = "strict"
    REPORT_ONLY = "report_only"

class RepairValidationError(ValueError):
    """Structured validation failure for repair policy/configuration."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def to_error(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "details": self.details,
            "retryable": False,
            "user_action_required": True,
        }


@dataclass(frozen=True)
class RepairSummary:
    """Caller-visible topology repair summary.

    Keep this shape aligned with ``schemas/direct_build.schema.json`` and
    ``schemas/realign.schema.json``. Additional internal diagnostics should live
    in warnings/details until they become part of the public contract.
    """

    holes_filled: int = 0
    contiguity_repairs: int = 0
    changed_part_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "holes_filled": self.holes_filled,
            "contiguity_repairs": self.contiguity_repairs,
            "changed_part_ids": list(self.changed_part_ids),
        }


@dataclass(frozen=True)
class RepairResult:
    """Result of applying a repair policy to dissolved territories."""

    hierarchy: DissolvedHierarchy
    policy: RepairPolicy
    summary: RepairSummary = field(default_factory=RepairSummary)
    warnings: tuple[dict[str, Any], ...] = ()

def parse_repair_policy(value: Any) -> RepairPolicy:
    """Parse a caller-supplied repair policy string."""
    raw = str(value or RepairPolicy.DEFAULT.value).strip() or RepairPolicy.DEFAULT.value
    try:
        return RepairPolicy(raw)
    except ValueError as exc:
        allowed = [policy.value for policy in RepairPolicy]
        raise RepairValidationError(
            "INVALID_REPAIR_POLICY",
            f"repair_policy must be one of: {', '.join(allowed)}.",
            {"repair_policy": raw, "allowed_values": allowed},
        ) from exc

def repair_dissolved_hierarchy(
    hierarchy: DissolvedHierarchy,
    *,
    policy: RepairPolicy | str | None = None,
) -> RepairResult:
    """Apply the selected repair policy to dissolved territory geometry.

    This first skeleton deliberately does not mutate geometry. It establishes the
    public policy/summary boundary and gives future phases one obvious place to
    add hole detection, gap assignment, and contiguity enforcement.
    """
    resolved_policy = parse_repair_policy(policy)
    changed_part_ids = _sorted_unique_part_ids(())
    return RepairResult(
        hierarchy=hierarchy,
        policy=resolved_policy,
        summary=RepairSummary(changed_part_ids=changed_part_ids),
    )

def _sorted_unique_part_ids(part_ids: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({str(part_id) for part_id in part_ids if str(part_id).strip()}))
