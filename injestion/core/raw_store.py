"""
Utility for pipelines: save raw API response to a JSON file for review.

Use when defining a new resource: fetch -> save raw -> review JSON -> define schema
and transform -> set up BQ table -> add table to .env -> switch pipeline to transform + write.
"""

import json
import os
from pathlib import Path


def save_raw_to_json(
    raw: dict,
    resource_name: str,
    source: str = "sportradar",
    base_dir: str | None = None,
) -> Path:
    """
    Write raw payload to {base_dir}/{source}/{resource_name}.json.
    Creates parent directories if needed. Returns the path written.
    Use from any pipeline to stash raw data before defining schema.
    base_dir defaults to RAW_DATA_DIR env or "raw_data".
    """
    if base_dir is None:
        base_dir = os.environ.get("RAW_DATA_DIR", "raw_data")
    out_dir = Path(base_dir) / source
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{resource_name}.json"
    with open(path, "w") as f:
        json.dump(raw, f, indent=2)
    return path
