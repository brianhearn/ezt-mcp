#!/usr/bin/env python3
"""Validate schemas/examples payloads against the corresponding schema $defs."""

from __future__ import annotations

import json
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=DeprecationWarning)

from jsonschema import Draft202012Validator, FormatChecker, RefResolver

SCHEMA_DIR = Path(__file__).resolve().parent
EXAMPLE_DIR = SCHEMA_DIR / "examples"


def load_json(path: Path):
    return json.loads(path.read_text())


def main() -> int:
    schemas = {path.name: load_json(path) for path in SCHEMA_DIR.glob("*.schema.json")}
    store = {}
    for schema in schemas.values():
        schema_id = schema.get("$id")
        if schema_id:
            store[schema_id] = schema
            store[schema_id.rsplit("/", 1)[-1]] = schema
    for name, schema in schemas.items():
        store[name] = schema

    manifest = load_json(EXAMPLE_DIR / "manifest.json")
    failures = []

    for item in manifest:
        example_path = EXAMPLE_DIR / item["file"]
        schema_name = item["schema"]
        definition = item["definition"]
        schema = schemas[schema_name]
        target_schema = schema["$defs"][definition]
        resolver = RefResolver.from_schema(schema, store=store)
        validator = Draft202012Validator(target_schema, resolver=resolver, format_checker=FormatChecker())
        errors = sorted(validator.iter_errors(load_json(example_path)), key=lambda e: list(e.path))
        if errors:
            failures.append((item, errors))
        else:
            print(f"ok {item['file']} -> {schema_name}#/$defs/{definition}")

    if failures:
        print("\nValidation failures:")
        for item, errors in failures:
            print(f"\n{item['file']} -> {item['schema']}#/$defs/{item['definition']}")
            for error in errors:
                loc = "/".join(str(p) for p in error.path) or "<root>"
                print(f"  - {loc}: {error.message}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
