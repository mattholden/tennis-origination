"""
Load and split the OddsJam-projected-games total-points modeling frame.

Reused by total_points_oj_line_dataset.ipynb workflows and MLE notebooks.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from google.cloud import bigquery

from injestion.sportradar import SportradarManager
from refined_tables import get_table_id

DEFAULT_TEST_CUTOFF = pd.Timestamp("2026-06-06", tz="UTC")
KEEP_MATCH_STATUSES = frozenset({"ended"})
# Drop bo3 rows with implausible OddsJam total-games lines (e.g. line ≥ 30).
BO3_MAX_PROJECTED_TOTAL_GAMES = 30.0
# Core tour levels only — drop sparse cups/finals/nulls from modeling data.
KEEP_COMPETITION_LEVELS = frozenset(
    {
        "atp_250",
        "atp_500",
        "atp_1000",
        "wta_250",
        "wta_500",
        "wta_1000",
        "grand_slam",
    }
)

UNIFIED_COLS = [
    "sport_event_id",
    "fixture_id",
    "total_points",
    "projected_total_games",
    "total_games_played",
    "category_name",
    "competition_level",
    "mode_best_of",
    "start_time",
    "competition_gender",
    "competition_name",
    "competition_id",
    "season_id",
    "season_name",
    "period_scores",
    "summary_match_status",
    "projected_total_games_over_price",
    "projected_total_games_under_price",
]


def assert_one_to_one(df: pd.DataFrame, col: str, label: str) -> None:
    dup = df[col].duplicated(keep=False)
    n = int(dup.sum())
    if n > 0:
        sample = df.loc[dup, col].astype(str).drop_duplicates().head(10).tolist()
        raise ValueError(f"{label} not 1:1 on {col}: {n} duplicate rows. Sample: {sample}")


def build_total_games_lines(consensus_tg: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    One row per fixture_id with projected_total_games.

    Excludes fixtures where over/under closing_line_points disagree.
    """
    work = consensus_tg.copy()
    work["selection_line_key"] = (
        work["selection_line_key"].astype("string").str.lower().str.strip()
    )

    nunique_points = work.groupby("fixture_id")["closing_line_points"].nunique(dropna=True)
    conflict_ids = set(nunique_points[nunique_points > 1].index.astype(str))
    excluded = work.loc[work["fixture_id"].astype(str).isin(conflict_ids)].copy()

    clean = work.loc[~work["fixture_id"].astype(str).isin(conflict_ids)].copy()
    if clean.empty:
        empty_cols = [
            "fixture_id",
            "projected_total_games",
            "projected_total_games_over_price",
            "projected_total_games_under_price",
        ]
        return pd.DataFrame(columns=empty_cols), excluded

    points = (
        clean.groupby("fixture_id", as_index=False)["closing_line_points"]
        .first()
        .rename(columns={"closing_line_points": "projected_total_games"})
    )
    over_price = (
        clean.loc[clean["selection_line_key"] == "over", ["fixture_id", "avg_closing_line_price"]]
        .drop_duplicates(subset=["fixture_id"], keep="first")
        .rename(columns={"avg_closing_line_price": "projected_total_games_over_price"})
    )
    under_price = (
        clean.loc[clean["selection_line_key"] == "under", ["fixture_id", "avg_closing_line_price"]]
        .drop_duplicates(subset=["fixture_id"], keep="first")
        .rename(columns={"avg_closing_line_price": "projected_total_games_under_price"})
    )
    lines = (
        points.merge(over_price, on="fixture_id", how="left")
        .merge(under_price, on="fixture_id", how="left")
        .dropna(subset=["projected_total_games"])
        .reset_index(drop=True)
    )
    return lines, excluded


def load_unified_match_df(
    client: bigquery.Client,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Build the joined match-level frame (pre status filter).

    Returns (unified_df, diagnostics).
    """
    mapping_table = get_table_id("fixture_id_mapping")
    fixture_stats_table = get_table_id("fixture_stats")
    consensus_table = get_table_id("consensus")
    event_summary_table = SportradarManager().get_table_id("event_summary")

    mapping_df = client.query(
        f"SELECT sport_event_id, fixture_id FROM `{mapping_table}`"
    ).to_dataframe()
    assert_one_to_one(mapping_df, "sport_event_id", "fixture_id_mapping")
    assert_one_to_one(mapping_df, "fixture_id", "fixture_id_mapping")

    fixture_stats_df = client.query(
        f"""
        SELECT
          sport_event_id,
          total_points,
          total_games_played,
          mode_best_of,
          summary_match_status
        FROM `{fixture_stats_table}`
        """
    ).to_dataframe()
    fixture_stats_df = fixture_stats_df.drop_duplicates(subset=["sport_event_id"], keep="first")
    assert_one_to_one(fixture_stats_df, "sport_event_id", "fixture_stats")

    consensus_tg_df = client.query(
        f"""
        SELECT
          fixture_id,
          market,
          market_id,
          selection_line_key,
          closing_line_points,
          avg_closing_line_price
        FROM `{consensus_table}`
        WHERE LOWER(market) = 'total games'
           OR LOWER(market_id) = 'total_games'
        """
    ).to_dataframe()
    total_games_lines, total_games_conflicts = build_total_games_lines(consensus_tg_df)

    event_summary_df = client.query(
        f"""
        SELECT
          sport_event_id,
          category_name,
          competition_level,
          start_time,
          competition_gender,
          competition_name,
          competition_id,
          season_id,
          season_name,
          period_scores
        FROM `{event_summary_table}`
        """
    ).to_dataframe()
    event_summary_df = event_summary_df.drop_duplicates(subset=["sport_event_id"], keep="first")
    assert_one_to_one(event_summary_df, "sport_event_id", "event_summary")

    n_map = len(mapping_df)
    step1 = mapping_df.merge(fixture_stats_df, on="sport_event_id", how="inner")
    step2 = step1.merge(total_games_lines, on="fixture_id", how="inner")
    unified_raw = step2.merge(event_summary_df, on="sport_event_id", how="left")
    unified_df = unified_raw.loc[:, UNIFIED_COLS].copy()
    assert_one_to_one(unified_df, "sport_event_id", "unified_df")
    assert_one_to_one(unified_df, "fixture_id", "unified_df")

    diagnostics = {
        "n_mapping": n_map,
        "n_with_stats": len(step1),
        "n_with_line": len(step2),
        "n_unified": len(unified_df),
        "n_total_games_conflicts": (
            int(total_games_conflicts["fixture_id"].nunique())
            if not total_games_conflicts.empty
            else 0
        ),
    }
    return unified_df, diagnostics


def filter_ended_matches(
    unified_df: pd.DataFrame,
    keep_statuses: frozenset[str] = KEEP_MATCH_STATUSES,
) -> pd.DataFrame:
    status_norm = unified_df["summary_match_status"].astype("string").str.lower().str.strip()
    return unified_df.loc[status_norm.isin(keep_statuses)].copy()


def filter_bo3_projected_games(
    match_df: pd.DataFrame,
    *,
    max_projected_games: float = BO3_MAX_PROJECTED_TOTAL_GAMES,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Keep best-of-3 rows only when projected_total_games < max_projected_games.

    Best-of-5 (and other) rows are unchanged. Bo3 rows with missing projected
    line are dropped by the same rule.
    """
    work = match_df.copy()
    mode = pd.to_numeric(work["mode_best_of"], errors="coerce")
    proj = pd.to_numeric(work["projected_total_games"], errors="coerce")
    is_bo3 = mode == 3
    drop_mask = is_bo3 & ~(proj < float(max_projected_games))
    n_dropped = int(drop_mask.sum())
    kept = work.loc[~drop_mask].copy()
    diagnostics = {
        "bo3_max_projected_total_games": float(max_projected_games),
        "n_bo3_before_proj_filter": int(is_bo3.sum()),
        "n_bo3_proj_filter_dropped": n_dropped,
        "n_bo3_after_proj_filter": int(is_bo3.sum()) - n_dropped,
    }
    return kept, diagnostics


def filter_competition_levels(
    match_df: pd.DataFrame,
    *,
    keep_levels: frozenset[str] = KEEP_COMPETITION_LEVELS,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Keep only core tour competition_level values (ATP/WTA 250–1000 + grand_slam).

    Drops sparse events (Tour Finals, Next Gen, null level, etc.) so they are
    not used for training or evaluation.
    """
    work = match_df.copy()
    level_norm = work["competition_level"].astype("string").str.lower().str.strip()
    keep_norm = {str(x).lower().strip() for x in keep_levels}
    keep_mask = level_norm.isin(keep_norm)
    dropped = work.loc[~keep_mask, "competition_level"].value_counts(dropna=False)
    kept = work.loc[keep_mask].copy()
    diagnostics = {
        "n_before_competition_level_filter": int(len(work)),
        "n_competition_level_filter_dropped": int((~keep_mask).sum()),
        "n_after_competition_level_filter": int(len(kept)),
        "dropped_competition_levels": {
            ("null" if pd.isna(k) else str(k)): int(v) for k, v in dropped.items()
        },
        "keep_competition_levels": sorted(keep_norm),
    }
    return kept, diagnostics


def apply_tournament_split(
    match_df: pd.DataFrame,
    *,
    test_cutoff: pd.Timestamp = DEFAULT_TEST_CUTOFF,
) -> dict[str, pd.DataFrame]:
    """
    Split by tournament first_match_date (season_id).

    Tournaments with first_match_date >= cutoff → test; else train.
    """
    split_base = match_df.copy()
    split_base["start_time"] = pd.to_datetime(split_base["start_time"], utc=True, errors="coerce")

    tournament_starts = (
        split_base.dropna(subset=["season_id", "start_time"])
        .groupby("season_id", as_index=False)
        .agg(
            season_name=("season_name", "first"),
            category_name=("category_name", "first"),
            competition_level=("competition_level", "first"),
            first_match_date=("start_time", "min"),
            n_matches=("sport_event_id", "size"),
        )
    )
    tournament_starts["split"] = np.where(
        tournament_starts["first_match_date"] >= test_cutoff, "test", "train"
    )

    split_base = split_base.merge(
        tournament_starts[["season_id", "first_match_date", "split"]],
        on="season_id",
        how="left",
    )
    return {
        "all": split_base,
        "train": split_base.loc[split_base["split"] == "train"].copy(),
        "test": split_base.loc[split_base["split"] == "test"].copy(),
        "tournaments": tournament_starts,
    }


def load_train_test_frames(
    client: bigquery.Client,
    *,
    test_cutoff: pd.Timestamp = DEFAULT_TEST_CUTOFF,
    bo3_max_projected_games: float = BO3_MAX_PROJECTED_TOTAL_GAMES,
    keep_competition_levels: frozenset[str] = KEEP_COMPETITION_LEVELS,
) -> dict[str, Any]:
    """End-to-end: unified → ended → level allowlist → bo3 proj → train/test."""
    unified_df, diagnostics = load_unified_match_df(client)
    ended_df = filter_ended_matches(unified_df)
    level_df, level_diag = filter_competition_levels(
        ended_df, keep_levels=keep_competition_levels
    )
    filtered_df, bo3_diag = filter_bo3_projected_games(
        level_df, max_projected_games=bo3_max_projected_games
    )
    diagnostics = {**diagnostics, **level_diag, **bo3_diag}
    splits = apply_tournament_split(filtered_df, test_cutoff=test_cutoff)
    return {
        "unified_df": unified_df,
        "ended_df": ended_df,
        "filtered_df": filtered_df,
        "train_df": splits["train"],
        "test_df": splits["test"],
        "all_split_df": splits["all"],
        "tournaments": splits["tournaments"],
        "diagnostics": diagnostics,
        "test_cutoff": test_cutoff,
    }
