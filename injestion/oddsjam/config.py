"""
OddsJam table IDs and resource config.

Reads from environment; ensure the entry point calls injestion.core.env.load_env() so .env is loaded.
API key and base URL are used by the OpticOdds client (OpticOdds API v3).
"""

import os

def get_api_key() -> str:
    """Return OpticOdds API key from environment. Raises if missing."""
    key = os.environ.get("ODDSJAM_API_KEY")
    if not key:
        raise ValueError(
            "ODDSJAM_API_KEY not set. Add one to .env in the project root."
        )
    return key.strip()


def get_base_url() -> str:
    """Base URL for OpticOdds API v3. Defaults to DEFAULT_BASE_URL if env not set."""
    base_url = os.environ.get("ODDSJAM_BASE_URL")
    if not base_url:
        raise ValueError(
            "ODDSJAM_BASE_URL not set. Add one to .env in the project root."
        )
    return base_url.strip().rstrip("/")


# Env var names for each resource's BigQuery table
TABLE_ID_ENV = {
    "oddsjam_odds": "BIGQUERY_ODDSJAM_ODDS_TABLE_ID",
    "oddsjam_results": "BIGQUERY_ODDSJAM_RESULTS_TABLE_ID",
    "oddsjam_fixtures": "BIGQUERY_ODDSJAM_FIXTURES_TABLE_ID",
    "oddsjam_seasons": "BIGQUERY_ODDSJAM_SEASONS_TABLE_ID",
}


def get_table_id(resource_name: str) -> str:
    """Return BigQuery table ID for the given resource. Raises if not set."""
    env_var = TABLE_ID_ENV.get(resource_name)
    if not env_var:
        raise ValueError(f"Unknown resource: {resource_name!r}")
    value = os.environ.get(env_var)
    if not value:
        raise ValueError(
            f"{env_var} not set. Add it to .env for the {resource_name} table."
        )
    return value.strip()