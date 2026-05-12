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
""".strip()
    )
    monkeypatch.setenv("EZT_MCP_API_KEY", "dev-key")

    config = load_config(path)

    assert config.host == "0.0.0.0"
    assert config.port == 8100
    assert config.database_url == "postgresql://example/db"
    assert config.auth.api_keys == ["dev-key"]
