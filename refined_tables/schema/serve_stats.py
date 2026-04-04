"""
Per-match / per-competitor serve statistics (match-level + flattened set columns).

Aligns with serve_stats_table from refined_tables notebooks: pandas object → STRING,
numeric columns as FLOAT64 (matches float64 dtypes when nulls are present).
"""

from google.cloud import bigquery

_MATCH_NUMERIC = (
    "first_serve_attempts",
    "first_serve_in",
    "first_serve_percentage",
    "second_serve_attempts",
    "second_serve_in",
    "second_serve_percentage",
)

_SET_NUMERIC = (
    "first_serve_attempts",
    "first_serve_in",
    "first_serve_percentage",
    "second_serve_attempts",
    "second_serve_in",
    "second_serve_percentage",
)


def get_schema() -> list[bigquery.SchemaField]:
    """BigQuery schema for serve_stats (grain: one row per sport_event_id × competitor_id)."""
    fields: list[bigquery.SchemaField] = [
        bigquery.SchemaField("sport_event_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("competitor_id", "STRING", mode="REQUIRED"),
    ]
    for name in _MATCH_NUMERIC:
        fields.append(bigquery.SchemaField(name, "FLOAT64", mode="NULLABLE"))
    for set_n in range(1, 6):
        for suffix in _SET_NUMERIC:
            fields.append(
                bigquery.SchemaField(f"set_{set_n}_{suffix}", "FLOAT64", mode="NULLABLE")
            )
    return fields
