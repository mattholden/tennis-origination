-- Replace your_project.your_dataset.consensus with BIGQUERY_REFINED_CONSENSUS_TABLE_ID.
-- Run in BigQuery console or: bq query --use_legacy_sql=false < create_consensus.sql

CREATE TABLE IF NOT EXISTS `your_project.your_dataset.consensus` (
  consensus_row_key STRING NOT NULL,
  fixture_id STRING NOT NULL,
  league_name STRING,
  start_date TIMESTAMP,
  status STRING,
  market STRING,
  market_id STRING,
  name STRING,
  selection STRING,
  normalized_selection STRING,
  selection_line STRING,
  normalized_selection_key STRING,
  selection_line_key STRING,
  player_id STRING,
  team_id STRING,
  closing_line_points FLOAT64,
  avg_closing_line_points FLOAT64,
  avg_closing_line_price FLOAT64,
  implied_win_prob FLOAT64,
  moneyline_competitiveness_metric FLOAT64,
  mode_best_of INT64,
  home_sets_won INT64,
  away_sets_won INT64,
  total_sets_from_result INT64
);
