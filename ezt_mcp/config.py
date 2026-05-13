"""Configuration for EZT MCP."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class DatabaseConfig(BaseModel):
    """Database connection settings."""

    url: str | None = None


class AuthConfig(BaseModel):
    """Simple API-key auth settings for the deploy/test server."""

    api_keys: list[str] = Field(default_factory=list)


class MapVisualizationConfig(BaseModel):
    """Browser-facing Map Component configuration."""

    public_base_url: str = "http://127.0.0.1:8000"


class ServerConfig(BaseModel):
    """Top-level server configuration."""

    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    map_visualization: MapVisualizationConfig = Field(default_factory=MapVisualizationConfig)

    @property
    def database_url(self) -> str | None:
        return self.database.url or os.environ.get("DATABASE_URL")


def load_config(config_path: str | Path) -> ServerConfig:
    """Load config from YAML plus environment fallbacks."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in config: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError("Config must be a YAML mapping")

    server_raw = raw.get("server", {}) or {}
    database_raw = raw.get("database", {}) or {}
    auth_raw = raw.get("auth", {}) or {}
    map_visualization_raw = raw.get("map_visualization", {}) or {}

    env_api_key = os.environ.get("EZT_MCP_API_KEY")
    api_keys = list(auth_raw.get("api_keys") or [])
    if env_api_key:
        api_keys.append(env_api_key)

    return ServerConfig(
        host=server_raw.get("host", "127.0.0.1"),
        port=int(server_raw.get("port", 8000)),
        log_level=server_raw.get("log_level", "info"),
        database=DatabaseConfig(url=database_raw.get("url")),
        auth=AuthConfig(api_keys=api_keys),
        map_visualization=MapVisualizationConfig(
            public_base_url=os.environ.get("EZT_MCP_PUBLIC_BASE_URL")
            or map_visualization_raw.get("public_base_url")
            or "http://127.0.0.1:8000"
        ),
    )
