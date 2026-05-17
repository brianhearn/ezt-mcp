from __future__ import annotations

from shapely.geometry import Polygon, mapping

import pytest

from ezt_mcp.map_component.sessions import (
    InMemoryMapSessionStore,
    MapVisualizationError,
    _resolved_theme,
    build_render_payload,
)


def square_feature(tal_id: str, territory_id: str, label: str, x: float, y: float):
    polygon = Polygon([(x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)])
    return {
        "type": "Feature",
        "properties": {
            "tal_id": tal_id,
            "territory_id": territory_id,
            "label": label,
            "is_leaf": True,
            "part_ids": [territory_id.upper()],
        },
        "geometry": mapping(polygon),
    }


def sample_ts():
    return {
        "type": "FeatureCollection",
        "properties": {
            "active_tal_id": "tal-current",
            "ts_identity": {
                "ts_id": "ts-demo",
                "revision": 3,
                "content_hash": "sha256:" + "1" * 64,
                "updated_at": "2026-05-13T18:30:00Z",
            },
            "territory_alignment_layers": [
                {"tal_id": "tal-current", "label": "Current Territories"}
            ],
        },
        "features": [
            square_feature("tal-current", "t-west", "West", -100, 35),
            square_feature("tal-current", "t-east", "East", -90, 36),
            square_feature("tal-other", "t-other", "Other", -80, 36),
        ],
    }


def test_build_render_payload_filters_active_tal_and_bounds():
    payload = build_render_payload(
        sample_ts(),
        active_tal_id="tal-current",
        mode="view",
        public_base_url="https://expertpack.ai/mcp",
    )

    assert payload["active_tal"] == {
        "tal_id": "tal-current",
        "label": "Current Territories",
        "territory_count": 2,
    }
    assert payload["bounds"] == [-100.0, 35.0, -79.0, 37.0]
    assert len(payload["geojson"]["features"]) == 2
    assert len(payload["reference_geojson"]["features"]) == 1
    assert payload["reference_tals"] == [
        {
            "tal_id": "tal-other",
            "territory_count": 1,
            "render_role": "reference",
        }
    ]
    assert payload["geojson"]["features"][0]["properties"]["_render_color"]
    assert payload["geojson"]["features"][0]["properties"]["_render_tal_role"] == "active"
    reference_role = payload["reference_geojson"]["features"][0]["properties"]["_render_tal_role"]
    assert reference_role == "reference"
    assert payload["geojson"]["features"][0]["properties"]["part_ids"] == '["T-WEST"]'
    assert payload["basemap"]["url"] == "https://expertpack.ai/mcp/assets/tiles/us-basemap.pmtiles"


def test_build_render_payload_sorts_leaf_labels_above_rollups():
    ts = {
        "type": "FeatureCollection",
        "properties": {
            "active_tal_id": "tal-current",
            "territory_alignment_layers": [
                {"tal_id": "tal-current", "label": "Current Territories"}
            ],
        },
        "features": [
            square_feature("tal-current", "rollup", "Smoke", 0, 0),
            square_feature("tal-current", "leaf-a", "North Central Florida", 0, 0),
            square_feature("tal-current", "leaf-b", "Northeast Florida", 2, 0),
        ],
    }
    ts["features"][0]["properties"].update({"is_leaf": False, "depth": 0})
    ts["features"][1]["properties"].update({"is_leaf": True, "depth": 1})
    ts["features"][2]["properties"].update({"is_leaf": True, "depth": 1})

    payload = build_render_payload(
        ts,
        active_tal_id="tal-current",
        mode="view",
        public_base_url="https://expertpack.ai/mcp",
    )

    labels = [feature["properties"]["_render_label"] for feature in payload["geojson"]["features"]]
    priorities = [
        feature["properties"]["_render_label_priority"]
        for feature in payload["geojson"]["features"]
    ]
    assert labels[:2] == ["North Central Florida", "Northeast Florida"]
    assert labels[-1] == "Smoke"
    assert priorities == [1, 1, 100]


def test_build_render_payload_applies_presentation_template_and_overrides():
    ts = sample_ts()
    ts["properties"]["presentation"] = {
        "views": {
            "qa_verification": {
                "title": "QA From TS",
                "panel": {
                    "summary_items": [{"label": "Source", "value": "TS"}]
                },
            }
        }
    }

    payload = build_render_payload(
        ts,
        active_tal_id="tal-current",
        mode="view",
        presentation={
            "view_name": "qa_verification",
            "style_overrides": {
                "debug_panel": False,
                "panel": {
                    "summary_items": [{"label": "Override", "value": "Request"}]
                },
            },
        },
        public_base_url="https://expertpack.ai/mcp",
    )

    assert payload["presentation"]["view_name"] == "qa_verification"
    assert payload["presentation"]["panel_template"] == "qa_verification"
    assert payload["presentation"]["title"] == "QA From TS"
    assert payload["presentation"]["debug_panel"] is False
    assert payload["presentation"]["panel"]["summary_items"] == [
        {"label": "Override", "value": "Request"}
    ]


def test_build_render_payload_defaults_select_mode_to_selection_template():
    payload = build_render_payload(
        sample_ts(),
        active_tal_id="tal-current",
        mode="select",
        public_base_url="https://expertpack.ai/mcp",
    )

    assert payload["presentation"]["panel_template"] == "selection"
    assert payload["presentation"]["debug_panel"] is False


def test_build_render_payload_includes_localizable_chrome_labels():
    ts = sample_ts()
    ts["properties"]["presentation"] = {
        "views": {
            "executive_review": {
                "chrome_labels": {
                    "active_alignment_label": "Escenario activo",
                    "reference_alignments_legend": "Otros escenarios",
                }
            }
        }
    }

    payload = build_render_payload(
        ts,
        active_tal_id="tal-current",
        mode="view",
        presentation={
            "view_name": "executive_review",
            "style_overrides": {
                "chrome_labels": {
                    "active_alignment_updated_status": "Escenario actualizado.",
                }
            },
        },
        public_base_url="https://expertpack.ai/mcp",
    )

    labels = payload["presentation"]["chrome_labels"]
    assert labels["active_alignment_label"] == "Escenario activo"
    assert labels["reference_alignments_legend"] == "Otros escenarios"
    assert labels["active_alignment_updated_status"] == "Escenario actualizado."
    assert labels["active_alignment_aria"] == "Active territory alignment"


def test_session_store_returns_new_tab_response_and_validates_token():
    store = InMemoryMapSessionStore()
    session = store.create_session(
        {
            "ts": sample_ts(),
            "mode": "view",
            "active_tal_id": "tal-current",
            "expiry_seconds": 900,
        },
        public_base_url="https://expertpack.ai/mcp",
    )

    result = session.response_result(public_base_url="https://expertpack.ai/mcp")

    assert result["map_url"].startswith("https://expertpack.ai/mcp/maps/session/")
    assert result["presentation"] == {
        "preferred_open": "new_tab",
        "embed_status": "experimental",
        "open_in_new_tab_recommended": True,
    }
    assert result["session_exists"] is False
    assert result["active_tal_summary"]["territory_count"] == 2
    assert store.get_session(session.map_session_id, session.token) is session


# ─── Theme tests ──────────────────────────────────────────────────────────────


def test_resolved_theme_defaults_to_dark():
    assert _resolved_theme({}) == "dark"
    assert _resolved_theme({"style_overrides": {}}) == "dark"
    assert _resolved_theme({"style_overrides": {"theme": "bogus"}}) == "dark"


def test_resolved_theme_light():
    assert _resolved_theme({"style_overrides": {"theme": "light"}}) == "light"


def test_resolved_theme_explicit_dark():
    assert _resolved_theme({"style_overrides": {"theme": "dark"}}) == "dark"


def test_resolved_theme_fallback():
    assert _resolved_theme({}, fallback="light") == "light"
    # explicit override wins over fallback
    assert _resolved_theme({"style_overrides": {"theme": "dark"}}, fallback="light") == "dark"


def test_build_render_payload_includes_theme_dark_by_default():
    payload = build_render_payload(
        sample_ts(),
        active_tal_id="tal-current",
        public_base_url="https://expertpack.ai/mcp",
    )
    assert payload["theme"] == "dark"


def test_build_render_payload_includes_theme_light():
    payload = build_render_payload(
        sample_ts(),
        active_tal_id="tal-current",
        public_base_url="https://expertpack.ai/mcp",
        theme="light",
    )
    assert payload["theme"] == "light"


def test_session_store_persists_theme_from_presentation():
    store = InMemoryMapSessionStore()
    session = store.create_session(
        {
            "ts": sample_ts(),
            "mode": "view",
            "active_tal_id": "tal-current",
            "presentation": {"style_overrides": {"theme": "light"}},
        },
        public_base_url="https://expertpack.ai/mcp",
    )
    assert session.theme == "light"
    assert session.render_payload["theme"] == "light"


def test_session_store_theme_defaults_to_dark_without_override():
    store = InMemoryMapSessionStore()
    session = store.create_session(
        {"ts": sample_ts(), "mode": "view", "active_tal_id": "tal-current"},
        public_base_url="https://expertpack.ai/mcp",
    )
    assert session.theme == "dark"
    assert session.render_payload["theme"] == "dark"


def test_session_store_theme_persists_across_refresh_without_re_specifying():
    """Theme set at creation is preserved on refresh if not overridden."""
    from datetime import UTC, datetime

    store = InMemoryMapSessionStore()
    now = datetime.now(tz=UTC)
    session = store.create_session(
        {
            "ts": sample_ts(),
            "mode": "view",
            "active_tal_id": "tal-current",
            "presentation": {"style_overrides": {"theme": "light"}},
        },
        public_base_url="https://expertpack.ai/mcp",
        now=now,
    )
    assert session.theme == "light"

    # Refresh without specifying theme — should retain "light" via fallback
    session.refresh_from_request(
        {"ts": sample_ts(), "mode": "view", "active_tal_id": "tal-current"},
        public_base_url="https://expertpack.ai/mcp",
        now=now,
    )
    assert session.theme == "light"
    assert session.render_payload["theme"] == "light"


def test_session_store_theme_can_be_changed_on_refresh():
    """Theme override on refresh replaces the stored theme."""
    from datetime import UTC, datetime

    store = InMemoryMapSessionStore()
    now = datetime.now(tz=UTC)
    session = store.create_session(
        {
            "ts": sample_ts(),
            "mode": "view",
            "active_tal_id": "tal-current",
            "presentation": {"style_overrides": {"theme": "light"}},
        },
        public_base_url="https://expertpack.ai/mcp",
        now=now,
    )
    assert session.theme == "light"

    session.refresh_from_request(
        {
            "ts": sample_ts(),
            "mode": "view",
            "active_tal_id": "tal-current",
            "presentation": {"style_overrides": {"theme": "dark"}},
        },
        public_base_url="https://expertpack.ai/mcp",
        now=now,
    )
    assert session.theme == "dark"
    assert session.render_payload["theme"] == "dark"


def test_session_store_rejects_truncated_unicode_token_without_type_error():
    store = InMemoryMapSessionStore()
    session = store.create_session(
        {"ts": sample_ts(), "mode": "view", "active_tal_id": "tal-current"},
        public_base_url="https://expertpack.ai/mcp",
    )

    with pytest.raises(MapVisualizationError) as exc:
        store.get_session(session.map_session_id, "abc…def")

    assert exc.value.code == "INVALID_TS_HANDLE"
