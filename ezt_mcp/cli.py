"""CLI entry point for EZT MCP."""

from __future__ import annotations

import logging
import sys

import click
import uvicorn

from .config import load_config
from .server import build_app


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.option("--log-file", "-l", default=None, help="Write logs to file")
def main(verbose: bool, log_file: str | None) -> None:
    """EasyTerritory MCP Server."""
    level = logging.DEBUG if verbose else logging.INFO
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


@main.command()
@click.option("--config", "-c", "config_path", required=True, help="Path to config YAML")
def serve(config_path: str) -> None:
    """Start the EZT MCP server."""
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        click.echo(f"Error loading config: {exc}", err=True)
        sys.exit(1)

    app = build_app(config)
    click.echo(f"Starting EZT MCP server on {config.host}:{config.port}")
    click.echo("Endpoints:")
    click.echo("  GET  /health")
    click.echo("  GET  /part-layers")
    click.echo("  GET  /part-layers/{part_layer}")
    click.echo("  POST /mcp (when reverse-proxied at /mcp)")
    uvicorn.run(app, host=config.host, port=config.port, log_level=config.log_level)


if __name__ == "__main__":
    main()
