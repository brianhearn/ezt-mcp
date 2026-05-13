"""query_parts tool implementation.

Returns public part metadata only. Geometry and internal storage details never leave
this module.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from ezt_mcp.resources.part_layers import UnknownPartLayerError, assert_no_forbidden_public_fields

DEFAULT_MAX_RESULTS = 100
SERVER_MAX_RESULTS = 1000


class QueryPartsError(ValueError):
    """Structured public error for query_parts."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
        user_action_required: bool = True,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}
        self.retryable = retryable
        self.user_action_required = user_action_required

    def to_envelope(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": str(self),
                "details": self.details,
                "retryable": self.retryable,
                "user_action_required": self.user_action_required,
            },
        }


@dataclass(frozen=True)
class QueryPartsRequest:
    """Validated query_parts request."""

    part_layer: str
    filter: dict[str, Any] | None = None
    part_ids: list[str] | None = None
    max_results: int = DEFAULT_MAX_RESULTS
    offset: int = 0

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "QueryPartsRequest":
        part_layer = payload.get("part_layer")
        if not isinstance(part_layer, str) or not part_layer.strip():
            raise QueryPartsError(
                "INVALID_REQUEST",
                "part_layer is required and must be a non-empty string.",
                details={"field": "part_layer"},
            )

        filter_payload = payload.get("filter")
        part_ids_payload = payload.get("part_ids")
        has_filter = filter_payload is not None
        has_part_ids = part_ids_payload is not None
        if has_filter == has_part_ids:
            raise QueryPartsError(
                "INVALID_REQUEST",
                "Exactly one of filter or part_ids is required.",
                details={"fields": ["filter", "part_ids"]},
            )

        parsed_filter: dict[str, Any] | None = None
        if has_filter:
            if not isinstance(filter_payload, Mapping) or not filter_payload:
                raise QueryPartsError(
                    "INVALID_REQUEST",
                    "filter must be a non-empty object.",
                    details={"field": "filter"},
                )
            parsed_filter = dict(filter_payload)

        parsed_part_ids: list[str] | None = None
        if has_part_ids:
            if not isinstance(part_ids_payload, list) or not part_ids_payload:
                raise QueryPartsError(
                    "INVALID_REQUEST",
                    "part_ids must be a non-empty array of strings.",
                    details={"field": "part_ids"},
                )
            parsed_part_ids = []
            for part_id in part_ids_payload:
                if not isinstance(part_id, str) or not part_id:
                    raise QueryPartsError(
                        "INVALID_REQUEST",
                        "part_ids must contain only non-empty strings.",
                        details={"field": "part_ids"},
                    )
                parsed_part_ids.append(part_id)

        max_results_raw = payload.get("max_results", DEFAULT_MAX_RESULTS)
        if not isinstance(max_results_raw, int) or isinstance(max_results_raw, bool):
            raise QueryPartsError(
                "INVALID_REQUEST",
                "max_results must be an integer.",
                details={"field": "max_results"},
            )
        max_results = min(max(max_results_raw, 1), SERVER_MAX_RESULTS)

        page_token = payload.get("page_token")
        offset = 0
        if page_token is not None:
            if not isinstance(page_token, str) or not page_token:
                raise QueryPartsError(
                    "INVALID_PAGE_TOKEN",
                    "page_token must be a non-empty string when provided.",
                    details={"field": "page_token"},
                )
            offset = decode_page_token(page_token, part_layer=part_layer.strip())

        return cls(
            part_layer=part_layer.strip(),
            filter=parsed_filter,
            part_ids=parsed_part_ids,
            max_results=max_results,
            offset=offset,
        )


class QueryPartsRepository(Protocol):
    """Repository protocol used by query_parts."""

    async def query_parts(self, request: QueryPartsRequest) -> dict[str, Any]: ...


async def query_parts_tool(repo: QueryPartsRepository, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Run query_parts and return a public tool envelope."""
    try:
        request = QueryPartsRequest.from_payload(payload)
        result = await repo.query_parts(request)
    except UnknownPartLayerError as exc:
        return QueryPartsError(
            exc.code,
            str(exc),
            details={"part_layer": exc.part_layer},
        ).to_envelope()
    except QueryPartsError as exc:
        return exc.to_envelope()

    assert_no_forbidden_public_fields(result)
    return {"ok": True, "result": result}


def encode_page_token(*, part_layer: str, offset: int) -> str:
    raw = json.dumps({"part_layer": part_layer, "offset": offset}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode_page_token(token: str, *, part_layer: str) -> int:
    try:
        padded = token + ("=" * (-len(token) % 4))
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise QueryPartsError(
            "INVALID_PAGE_TOKEN",
            "page_token is malformed.",
            details={"field": "page_token"},
        ) from exc

    if not isinstance(data, dict) or data.get("part_layer") != part_layer:
        raise QueryPartsError(
            "INVALID_PAGE_TOKEN",
            "page_token does not match the requested part_layer.",
            details={"field": "page_token", "part_layer": part_layer},
        )
    offset = data.get("offset")
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise QueryPartsError(
            "INVALID_PAGE_TOKEN",
            "page_token contains an invalid offset.",
            details={"field": "page_token"},
        )
    return offset
