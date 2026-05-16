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


class DissolveConfig(BaseModel):
    """Territory dissolve tuning."""

    simplify_tolerance: float = 0.0
    overview_simplify_tolerance: float = 0.0
    partition_threshold: int = 10000
    target_parts_per_cluster: int = 100
    max_clusters: int = 30


class JobsConfig(BaseModel):
    """Transient async job limits and retry behavior."""

    max_queued_jobs_per_customer: int = 100
    max_active_jobs_per_customer: int = 20
    max_attempts: int = 3
    retry_backoff_seconds: int = 60


class ServerConfig(BaseModel):
    """Top-level server configuration."""

    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    map_visualization: MapVisualizationConfig = Field(default_factory=MapVisualizationConfig)
    dissolve: DissolveConfig = Field(default_factory=DissolveConfig)
    jobs: JobsConfig = Field(default_factory=JobsConfig)

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
    dissolve_raw = raw.get("dissolve", {}) or {}
    jobs_raw = raw.get("jobs", {}) or {}

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
        dissolve=DissolveConfig(
            simplify_tolerance=float(
                os.environ.get("EZT_MCP_DISSOLVE_SIMPLIFY_TOLERANCE")
                or dissolve_raw.get("simplify_tolerance")
                or 0.0
            ),
            overview_simplify_tolerance=float(
                os.environ.get("EZT_MCP_DISSOLVE_OVERVIEW_SIMPLIFY_TOLERANCE")
                or dissolve_raw.get("overview_simplify_tolerance")
                or 0.0
            ),
            partition_threshold=int(
                os.environ.get("EZT_MCP_DISSOLVE_PARTITION_THRESHOLD")
                or dissolve_raw.get("partition_threshold")
                or 10000
            ),
            target_parts_per_cluster=int(
                os.environ.get("EZT_MCP_DISSOLVE_TARGET_PARTS_PER_CLUSTER")
                or dissolve_raw.get("target_parts_per_cluster")
                or 100
            ),
            max_clusters=int(
                os.environ.get("EZT_MCP_DISSOLVE_MAX_CLUSTERS")
                or dissolve_raw.get("max_clusters")
                or 30
            ),
        ),
        jobs=JobsConfig(
            max_queued_jobs_per_customer=int(
                os.environ.get("EZT_MCP_MAX_QUEUED_JOBS_PER_CUSTOMER")
                or jobs_raw.get("max_queued_jobs_per_customer")
                or 100
            ),
            max_active_jobs_per_customer=int(
                os.environ.get("EZT_MCP_MAX_ACTIVE_JOBS_PER_CUSTOMER")
                or jobs_raw.get("max_active_jobs_per_customer")
                or 20
            ),
            max_attempts=int(
                os.environ.get("EZT_MCP_JOB_MAX_ATTEMPTS")
                or jobs_raw.get("max_attempts")
                or 3
            ),
            retry_backoff_seconds=int(
                os.environ.get("EZT_MCP_JOB_RETRY_BACKOFF_SECONDS")
                or jobs_raw.get("retry_backoff_seconds")
                or 60
            ),
        ),
    )
