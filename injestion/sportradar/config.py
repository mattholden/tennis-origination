"""
Sportradar table IDs and resource config.

Reads from environment; ensure the entry point calls injestion.core.env.load_env() so .env is loaded.
"""

import os


# Env var names for each resource's BigQuery table
TABLE_ID_ENV = {
    "competitions": "BIGQUERY_SR_COMPETITIONS_TABLE_ID",
    "seasons": "BIGQUERY_SR_SEASONS_TABLE_ID",
    "season_competitors": "BIGQUERY_SR_SEASON_COMPETITORS_TABLE_ID",
    "competitors": "BIGQUERY_SR_COMPETITORS_TABLE_ID",
    "surface_stats": "BIGQUERY_SR_SURFACE_STATS_TABLE_ID",
    "season_brackets": "BIGQUERY_SR_SEASON_BRACKETS_TABLE_ID",
    "event_summary": "BIGQUERY_SR_EVENT_SUMMARY_TABLE_ID",
    "event_statistics": "BIGQUERY_SR_EVENT_STATISTICS_TABLE_ID",
    "event_timeline": "BIGQUERY_SR_EVENT_TIMELINE_TABLE_ID",
    "rankings": "BIGQUERY_SR_RANKINGS_TABLE_ID",
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
