"""Territory hierarchy materialization for Direct Build.

This module turns Direct Build assignment rows into a clean rollup tree before any
geometry work happens. It intentionally enforces the v1 leaf-only rule: a node
may either hold parts directly or have children, never both.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

MAX_TERRITORY_DEPTH = 4
MAX_PATH_LABELS = MAX_TERRITORY_DEPTH + 1


class HierarchyValidationError(ValueError):
    """Structured validation failure for hierarchy materialization."""

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
class HierarchyWarning:
    """Non-fatal hierarchy materialization warning."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


@dataclass
class TerritoryNode:
    """One materialized territory or rollup node."""

    label: str
    path: tuple[str, ...]
    key_path: tuple[str, ...]
    depth: int
    parent: "TerritoryNode | None" = None
    territory_id: str | None = None
    children: dict[str, "TerritoryNode"] = field(default_factory=dict)
    part_ids: list[str] = field(default_factory=list)

    @property
    def parent_territory_id(self) -> str | None:
        return self.parent.territory_id if self.parent else None

    @property
    def is_leaf(self) -> bool:
        return bool(self.part_ids)

    def to_properties(self, tal_id: str) -> dict[str, Any]:
        if self.territory_id is None:  # pragma: no cover - defensive guard
            raise RuntimeError("territory_id has not been assigned")
        return {
            "territory_id": self.territory_id,
            "label": self.label,
            "tal_id": tal_id,
            "depth": self.depth,
            "parent_territory_id": self.parent_territory_id,
            "is_leaf": self.is_leaf,
            "part_ids": list(self.part_ids),
        }


@dataclass(frozen=True)
class TerritoryHierarchy:
    """Materialized territory tree plus summary metadata."""

    tal_id: str
    roots: tuple[TerritoryNode, ...]
    nodes: tuple[TerritoryNode, ...]
    warnings: tuple[HierarchyWarning, ...] = ()

    @property
    def leaf_nodes(self) -> tuple[TerritoryNode, ...]:
        return tuple(node for node in self.nodes if node.is_leaf)

    @property
    def rollup_nodes(self) -> tuple[TerritoryNode, ...]:
        return tuple(node for node in self.nodes if not node.is_leaf)

    @property
    def max_depth(self) -> int:
        return max((node.depth for node in self.nodes), default=0)

    def summary(self) -> dict[str, int]:
        return {
            "max_depth": self.max_depth,
            "leaf_territory_count": len(self.leaf_nodes),
            "rollup_territory_count": len(self.rollup_nodes),
        }

    def territory_properties(self) -> list[dict[str, Any]]:
        return [node.to_properties(self.tal_id) for node in self.nodes]


def materialize_assignment_tree(
    assignments: Iterable[Mapping[str, Any]],
    *,
    tal_id: str,
) -> TerritoryHierarchy:
    """Build a deterministic territory tree from Direct Build assignment rows.

    Duplicate part policy follows the Technical Spec: duplicate rows are allowed
    only when they map to the same terminal leaf path. In that case the part is
    de-duplicated and a warning is returned. Conflicting duplicates fail with
    ``CLARIFICATION_REQUIRED``.
    """
    if not tal_id or not str(tal_id).strip():
        raise HierarchyValidationError(
            "CLARIFICATION_REQUIRED",
            "tal_id is required to materialize a territory hierarchy.",
        )

    roots: dict[str, TerritoryNode] = {}
    part_assignments: dict[str, tuple[str, ...]] = {}
    duplicate_rows: list[dict[str, Any]] = []

    for row_index, assignment in enumerate(assignments):
        part_id = _clean_part_id(assignment.get("part_id"), row_index)
        labels = _clean_path(assignment.get("territory_path"), row_index, part_id)
        key_path = tuple(_identity_label(label) for label in labels)

        previous_path = part_assignments.get(part_id)
        if previous_path is not None:
            if previous_path != key_path:
                raise HierarchyValidationError(
                    "CLARIFICATION_REQUIRED",
                    f"Part {part_id!r} is assigned to more than one territory path.",
                    {
                        "part_id": part_id,
                        "previous_territory_path": list(previous_path),
                        "conflicting_territory_path": list(key_path),
                        "row_index": row_index,
                    },
                )
            duplicate_rows.append(
                {
                    "part_id": part_id,
                    "territory_path": list(labels),
                    "row_index": row_index,
                }
            )
            continue

        node = _insert_path(roots, labels, key_path, part_id, row_index)
        node.part_ids.append(part_id)
        part_assignments[part_id] = key_path

    root_nodes = tuple(roots[key] for key in sorted(roots))
    ordered_nodes = tuple(_iter_nodes_depth_first(root_nodes))
    _assign_territory_ids(ordered_nodes, tal_id=str(tal_id))

    warnings: list[HierarchyWarning] = []
    if duplicate_rows:
        warnings.append(
            HierarchyWarning(
                code="DUPLICATE_PART_ASSIGNMENT_DEDUPED",
                message="Duplicate part assignment rows mapped to the same leaf and were de-duplicated.",
                details={"duplicates": duplicate_rows, "duplicate_count": len(duplicate_rows)},
            )
        )

    return TerritoryHierarchy(
        tal_id=str(tal_id),
        roots=root_nodes,
        nodes=ordered_nodes,
        warnings=tuple(warnings),
    )


def _insert_path(
    roots: dict[str, TerritoryNode],
    labels: tuple[str, ...],
    key_path: tuple[str, ...],
    part_id: str,
    row_index: int,
) -> TerritoryNode:
    children = roots
    parent: TerritoryNode | None = None
    node: TerritoryNode | None = None

    for depth, (label, key) in enumerate(zip(labels, key_path, strict=True)):
        child_key_path = key_path[: depth + 1]
        node = children.get(key)
        if node is None:
            node = TerritoryNode(
                label=label,
                path=labels[: depth + 1],
                key_path=child_key_path,
                depth=depth,
                parent=parent,
            )
            children[key] = node
        elif node.part_ids and depth < len(labels) - 1:
            raise HierarchyValidationError(
                "CLARIFICATION_REQUIRED",
                "A territory path cannot use an existing leaf territory as a rollup parent.",
                {
                    "part_id": part_id,
                    "existing_leaf_path": list(node.path),
                    "conflicting_territory_path": list(labels),
                    "row_index": row_index,
                },
            )

        parent = node
        children = node.children

    if node is None:  # pragma: no cover - path validation prevents this
        raise RuntimeError("empty territory path")

    if node.children:
        raise HierarchyValidationError(
            "CLARIFICATION_REQUIRED",
            "A territory path cannot assign parts directly to a rollup territory.",
            {
                "part_id": part_id,
                "rollup_path": list(node.path),
                "row_index": row_index,
            },
        )

    return node


def _assign_territory_ids(nodes: tuple[TerritoryNode, ...], *, tal_id: str) -> None:
    used: dict[str, int] = {}
    for node in nodes:
        path_slug = "-".join(_slugify(label) for label in node.path)
        base = f"{_slugify(tal_id)}-{path_slug}" if path_slug else _slugify(tal_id)
        count = used.get(base, 0) + 1
        used[base] = count
        node.territory_id = base if count == 1 else f"{base}-{count}"


def _iter_nodes_depth_first(nodes: Iterable[TerritoryNode]) -> Iterable[TerritoryNode]:
    for node in nodes:
        yield node
        yield from _iter_nodes_depth_first(node.children[key] for key in sorted(node.children))


def _clean_part_id(value: Any, row_index: int) -> str:
    if value is None or not str(value).strip():
        raise HierarchyValidationError(
            "CLARIFICATION_REQUIRED",
            "Each assignment row must include a non-empty part_id.",
            {"row_index": row_index},
        )
    return str(value).strip()


def _clean_path(value: Any, row_index: int, part_id: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise HierarchyValidationError(
            "CLARIFICATION_REQUIRED",
            "territory_path must be an array of 1 to 5 non-empty labels.",
            {"part_id": part_id, "row_index": row_index},
        )
    if not 1 <= len(value) <= MAX_PATH_LABELS:
        raise HierarchyValidationError(
            "CLARIFICATION_REQUIRED",
            "territory_path must contain 1 to 5 labels.",
            {"part_id": part_id, "row_index": row_index, "path_length": len(value)},
        )

    labels: list[str] = []
    for depth, label in enumerate(value):
        if label is None or not str(label).strip():
            raise HierarchyValidationError(
                "CLARIFICATION_REQUIRED",
                "territory_path labels must be non-empty strings.",
                {"part_id": part_id, "row_index": row_index, "depth": depth},
            )
        labels.append(_display_label(str(label)))
    return tuple(labels)


def _display_label(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _identity_label(value: str) -> str:
    return _display_label(value).casefold()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "territory"
