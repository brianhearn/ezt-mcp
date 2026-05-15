#!/usr/bin/env python3
"""Idempotent migration to add transient.map_sessions table for durable map sessions."""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
from dotenv import load_dotenv  # optional, falls back to env var


async def main() -> None:
    load_dotenv()  # loads .env from cwd or parent if present
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not found in environment or .env")
        sys.exit(1)

    print(f"Connecting to {database_url.split('@')[-1] if '@' in database_url else database_url}")

    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(
            """
            CREATE SCHEMA IF NOT EXISTS transient;
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS transient.map_sessions (
                map_session_id   TEXT PRIMARY KEY,
                token            TEXT NOT NULL,
                user_id          TEXT NOT NULL,
                mode             TEXT NOT NULL,
                theme            TEXT NOT NULL DEFAULT 'dark',
                active_tal_id    TEXT NOT NULL,
                active_tal_label TEXT,
                ts_identity      JSONB NOT NULL,
                render_payload   JSONB NOT NULL,
                ts               JSONB NOT NULL,
                presentation     JSONB NOT NULL DEFAULT '{}',
                public_base_url  TEXT NOT NULL DEFAULT '',
                state_resource_uri        TEXT NOT NULL,
                selection_resource_uri    TEXT,
                pending_job_reference     JSONB,
                committed_selection       JSONB,
                active_selection_task_id  TEXT,
                created_at       TIMESTAMPTZ NOT NULL,
                updated_at       TIMESTAMPTZ,
                expires_at       TIMESTAMPTZ NOT NULL
            );
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_map_sessions_user_id 
            ON transient.map_sessions (user_id);
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_map_sessions_expires_at 
            ON transient.map_sessions (expires_at);
            """
        )

        # Grant to the app user (idempotent)
        await conn.execute(
            """
            GRANT USAGE ON SCHEMA transient TO ezt_mcp_app;
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA transient TO ezt_mcp_app;
            """
        )

        print("Migration complete. transient.map_sessions table and indexes are ready.")
        print("Table columns match the MapVisualizationSession dataclass (JSONB for complex fields).")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
