"""
Sportradar table IDs and resource config.
"""

import os
from pathlib import Path


def _load_dotenv() -> None:
    try:
        import dotenv
        root = Path(__file__).resolve().parent.parent.parent
        dotenv.load_dotenv(root / ".env")
    except ImportError:
        pass


# Env var names for each resource's BigQuery table
TABLE_ID_ENV = {
    "competitions": "BIGQUERY_SR_COMPETITIONS_TABLE_ID",
    # "seasons": "BIGQUERY_SR_SEASONS_TABLE_ID",
}


def get_table_id(resource_name: str) -> str:
    """Return BigQuery table ID for the given resource. Raises if not set."""
    _load_dotenv()
    env_var = TABLE_ID_ENV.get(resource_name)
    if not env_var:
        raise ValueError(f"Unknown resource: {resource_name!r}")
    value = os.environ.get(env_var)
    if not value:
        raise ValueError(
            f"{env_var} not set. Add it to .env for the {resource_name} table."
        )
    return value.strip()
