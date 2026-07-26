"""
Fixture/market/selection-level consensus table schema.

This schema aligns with refined_tables/consensus.ipynb output.
"""

from google.cloud import bigquery


def get_schema() -> list[bigquery.SchemaField]:
    """BigQuery schema for refined consensus rows."""
    return [
        bigquery.SchemaField("consensus_row_key", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("fixture_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("league_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("start_date", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("status", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("market", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("market_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("selection", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("normalized_selection", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("selection_line", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("normalized_selection_key", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("selection_line_key", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("player_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("team_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("closing_line_points", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("avg_closing_line_points", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("avg_closing_line_price", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("implied_win_prob", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("moneyline_competitiveness_metric", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("mode_best_of", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("home_sets_won", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("away_sets_won", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("total_sets_from_result", "INTEGER", mode="NULLABLE"),
    ]
