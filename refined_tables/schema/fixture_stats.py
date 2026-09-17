"""
Fixture-level refined statistics for tennis pregame modeling.

This schema aligns with the `fixture_features` DataFrame built in
refined_tables/fixtures.ipynb (grain: one row per sport_event_id).
"""

from google.cloud import bigquery


def get_schema() -> list[bigquery.SchemaField]:
    """BigQuery schema for refined fixture stats (one row per match)."""
    return [
        bigquery.SchemaField("sport_event_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("total_points", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("total_rows_in_pbp", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("point_rows", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("period_score_rows", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("total_serve_holds", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("total_serve_breaks", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("first_event_time", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("last_event_time", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("mode_best_of", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("total_sets", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("match_status", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("home_competitor_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("away_competitor_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("home_competitor_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("away_competitor_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("total_games_played", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("total_tiebreaks_played", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("summary_competition_type", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("summary_match_status", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("summary_home_sets", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("summary_away_sets", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("summary_mode_best_of", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("period_score_matches_total_games", "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("break_rate", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("min_possible_points", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("violates_min_points", "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("total_aces_match", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("serve_stats_rows", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("non_null_ace_rows", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("ace_rate", "FLOAT64", mode="NULLABLE"),
    ]
