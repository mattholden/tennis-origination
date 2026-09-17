"""
Environment variable names for refined-table BigQuery destinations.

Set these in .env (see env var values in TABLE_ID_ENV). Names are logical keys
used by get_table_id("serve_stats"), etc.
"""

import os

# Env var name -> logical resource key is inverted: we map logical key -> env var
TABLE_ID_ENV: dict[str, str] = {
    "cleaned_pbp_with_server": "BIGQUERY_REFINED_CLEANED_PBP_WITH_SERVER_TABLE_ID",
    "consensus": "BIGQUERY_REFINED_CONSENSUS_TABLE_ID",
    "fixture_stats": "BIGQUERY_REFINED_FIXTURE_STATS_TABLE_ID",
    "serve_stats": "BIGQUERY_REFINED_SERVE_STATS_TABLE_ID",
}


def get_table_id(resource_name: str) -> str:
    """Return fully qualified BigQuery table id (project.dataset.table)."""
    env_var = TABLE_ID_ENV.get(resource_name)
    if not env_var:
        raise ValueError(
            f"Unknown refined table resource: {resource_name!r}. "
            f"Known: {list(TABLE_ID_ENV.keys())}"
        )
    value = os.environ.get(env_var)
    if not value:
        raise ValueError(
            f"{env_var} is not set. Add it to .env for refined table {resource_name!r}."
        )
    return value.strip()
