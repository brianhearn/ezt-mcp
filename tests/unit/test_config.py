from __future__ import annotations

from pathlib import Path

from ezt_mcp.config import load_config


def test_load_config_with_env_api_key(tmp_path: Path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
server:
  host: 0.0.0.0
  port: 8100
database:
  url: postgresql://example/db
map_visualization:
  public_base_url: https://example.com/mcp
""".strip()
    )
    monkeypatch.setenv("EZT_MCP_API_KEY", "dev-key")

    config = load_config(path)

    assert config.host == "0.0.0.0"
    assert config.port == 8100
    assert config.database_url == "postgresql://example/db"
    assert config.auth.api_keys == ["dev-key"]
    assert config.map_visualization.public_base_url == "https://example.com/mcp"


def test_load_config_public_base_url_env_override(tmp_path: Path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text("server: {}")
    monkeypatch.setenv("EZT_MCP_PUBLIC_BASE_URL", "https://expertpack.ai/mcp")

    config = load_config(path)

    assert config.map_visualization.public_base_url == "https://expertpack.ai/mcp"


def test_load_config_dissolve_settings(tmp_path: Path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
dissolve:
  simplify_tolerance: 0.001
  overview_simplify_tolerance: 0.008
  partition_threshold: 120
  target_parts_per_cluster: 80
  max_clusters: 25
""".strip()
    )
    monkeypatch.setenv("EZT_MCP_DISSOLVE_MAX_CLUSTERS", "30")

    config = load_config(path)

    assert config.dissolve.simplify_tolerance == 0.001
    assert config.dissolve.overview_simplify_tolerance == 0.008
    assert config.dissolve.partition_threshold == 120
    assert config.dissolve.target_parts_per_cluster == 80
    assert config.dissolve.max_clusters == 30
