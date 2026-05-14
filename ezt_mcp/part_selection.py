"""First-class part-selection task primitives.

Part selection is separate from Map Component session state: the MC commits
selected part IDs, while this task record gives agents a durable workflow handle
for polling/subscribing and later mutation tools.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Mapping

from .jobs import CustomerContext

SelectionStatus = Literal["awaiting_user_selection", "committed", "expired", "cancelled"]
SelectionPurpose = Literal["build_territory", "realign", "analyze", "return_list", "generic"]

TERMINAL_SELECTION_STATUSES: set[str] = {"committed", "expired", "cancelled"}
DEFAULT_SELECTION_TTL_SECONDS = 3600
VALID_SELECTION_PURPOSES: set[str] = {
    "build_territory",
    "realign",
    "analyze",
    "return_list",
    "generic",
}


class PartSelectionAccessError(PermissionError):
    """Raised when a caller cannot access a part-selection task."""

    def __init__(self, selection_task_id: str):
        super().__init__("Part-selection task was not found for this customer.")
        self.selection_task_id = selection_task_id
        self.code = "UNKNOWN_SELECTION_TASK"


class InvalidPartSelectionError(ValueError):
    """Raised when a part-selection request or commit is invalid."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass
class PartSelectionTask:
    """Short-lived first-class human spatial selection task."""

    selection_task_id: str
    customer_id: str
    user_id: str
    part_layer: str
    purpose: SelectionPurpose
    status: SelectionStatus
    map_session_id: str
    map_url: str
    selection_resource_uri: str
    created_at: datetime
    expires_at: datetime
    key_id: str | None = None
    prompt: str | None = None
    active_tal_id: str | None = None
    ts_identity: dict[str, Any] | None = None
    committed_selection: dict[str, Any] | None = None
    committed_at: datetime | None = None

    def reference(self, *, session_exists: bool = False) -> dict[str, Any]:
        return _drop_none(
            {
                "selection_task_id": self.selection_task_id,
                "status": self._effective_status(),
                "purpose": self.purpose,
                "part_layer": self.part_layer,
                "prompt": self.prompt,
                "map_session_id": self.map_session_id,
                "map_url": self.map_url,
                "selection_resource_uri": self.selection_resource_uri,
                "state_resource_uri": f"ezt://map-sessions/{self.map_session_id}/state",
                "session_exists": session_exists,
                "active_tal_id": self.active_tal_id,
                "ts_identity": self.ts_identity,
                "created_at": _isoformat_z(self.created_at),
                "expires_at": _isoformat_z(self.expires_at),
            }
        )

    def resource(self) -> dict[str, Any]:
        status = self._effective_status()
        payload = {
            "selection_task_id": self.selection_task_id,
            "status": status,
            "purpose": self.purpose,
            "part_layer": self.part_layer,
            "prompt": self.prompt,
            "map_session_id": self.map_session_id,
            "active_tal_id": self.active_tal_id,
            "ts_identity": self.ts_identity,
            "created_at": _isoformat_z(self.created_at),
            "expires_at": _isoformat_z(self.expires_at),
        }
        if self.committed_selection is not None:
            payload["selection"] = self.committed_selection
            payload["committed_at"] = _isoformat_z(self.committed_at)
        return _drop_none(payload)

    def _effective_status(self, *, now: datetime | None = None) -> SelectionStatus:
        now = now or datetime.now(tz=UTC)
        if self.status not in TERMINAL_SELECTION_STATUSES and now >= self.expires_at:
            return "expired"
        return self.status


class InMemoryPartSelectionRepository:
    """Customer-scoped in-memory selection task repository for the MVP skeleton."""

    def __init__(self) -> None:
        self._tasks: dict[str, PartSelectionTask] = {}

    def create(
        self,
        context: CustomerContext,
        *,
        user_id: str,
        part_layer: str,
        purpose: str,
        map_session_id: str,
        map_url: str,
        prompt: str | None = None,
        active_tal_id: str | None = None,
        ts_identity: Mapping[str, Any] | None = None,
        ttl_seconds: int = DEFAULT_SELECTION_TTL_SECONDS,
        now: datetime | None = None,
    ) -> PartSelectionTask:
        now = now or datetime.now(tz=UTC)
        if not part_layer:
            raise InvalidPartSelectionError(
                "INVALID_REQUEST", "request_part_selection requires a non-empty part_layer."
            )
        if purpose not in VALID_SELECTION_PURPOSES:
            raise InvalidPartSelectionError(
                "INVALID_REQUEST",
                "Unsupported part-selection purpose.",
                {"purpose": purpose, "allowed": sorted(VALID_SELECTION_PURPOSES)},
            )
        selection_task_id = f"psel_{secrets.token_urlsafe(18)}"
        task = PartSelectionTask(
            selection_task_id=selection_task_id,
            customer_id=context.customer_id,
            key_id=context.key_id,
            user_id=user_id or "default-user",
            part_layer=part_layer,
            purpose=purpose,  # type: ignore[arg-type]
            status="awaiting_user_selection",
            map_session_id=map_session_id,
            map_url=map_url,
            selection_resource_uri=f"ezt://part-selections/{selection_task_id}",
            prompt=prompt,
            active_tal_id=active_tal_id,
            ts_identity=dict(ts_identity) if ts_identity else None,
            created_at=now,
            expires_at=now + timedelta(seconds=_bounded_ttl(ttl_seconds)),
        )
        self._tasks[selection_task_id] = task
        return task

    def get(
        self,
        context: CustomerContext,
        selection_task_id: str,
        *,
        now: datetime | None = None,
    ) -> PartSelectionTask:
        task = self._tasks.get(selection_task_id)
        if task is None or task.customer_id != context.customer_id:
            raise PartSelectionAccessError(selection_task_id)
        effective = task._effective_status(now=now)
        if effective == "expired" and task.status != "expired":
            task.status = "expired"
        return task

    def commit(
        self,
        context: CustomerContext,
        selection_task_id: str,
        selection: Mapping[str, Any],
        *,
        now: datetime | None = None,
    ) -> PartSelectionTask:
        now = now or datetime.now(tz=UTC)
        task = self.get(context, selection_task_id, now=now)
        if task.status in {"expired", "cancelled"}:
            raise InvalidPartSelectionError(
                "INVALID_SELECTION",
                "Cannot commit a selection to an expired or cancelled selection task.",
                {"selection_task_id": selection_task_id, "status": task.status},
            )
        part_ids = selection.get("part_ids")
        if not isinstance(part_ids, list) or not all(
            isinstance(item, str) and item for item in part_ids
        ):
            raise InvalidPartSelectionError(
                "INVALID_SELECTION", "Selection commit requires a non-empty part_ids array."
            )
        part_layer = selection.get("part_layer") or task.part_layer
        if part_layer != task.part_layer:
            raise InvalidPartSelectionError(
                "INVALID_SELECTION",
                "Selection part_layer does not match the selection task part_layer.",
                {
                    "selection_task_id": selection_task_id,
                    "expected_part_layer": task.part_layer,
                    "actual_part_layer": part_layer,
                },
            )
        payload = {
            "type": "part_selection",
            "selection_task_id": selection_task_id,
            "purpose": task.purpose,
            "part_layer": task.part_layer,
            "part_ids": list(dict.fromkeys(part_ids)),
            "selection_method": selection.get("selection_method"),
            "map_session_id": task.map_session_id,
            "committed_at": _isoformat_z(now),
        }
        task.status = "committed"
        task.committed_at = now
        task.committed_selection = _drop_none(payload)
        return task


def _bounded_ttl(value: int | None) -> int:
    if value is None:
        return DEFAULT_SELECTION_TTL_SECONDS
    return max(60, min(int(value), 86400))


def _isoformat_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _drop_none(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}
