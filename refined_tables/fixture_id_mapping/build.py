"""
Build Sportradar sport_event_id ↔ OddsJam fixture_id crosswalk.

Match on both-player sorted-token name sets within a time window, then keep
mutual best matches only (1:1 both directions).
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

INVALID_PLAYER_KEYS = frozenset({"", "combined_market", "unknown_selection"})
DEFAULT_TIME_WINDOW_HOURS = 12.0
DEFAULT_TIME_MARGIN_MINUTES = 120.0
MATCH_METHOD = "both_players_token_set"


def normalize_player_name(value: Any) -> str | None:
    """
    Lowercase, split on non-alphanumeric, sort tokens, join with '_'.

    Order-independent so 'Wong, Hong Yi Cody' and 'hong_yi_cody_wong' align.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    tokens = [t for t in re.split(r"[^a-z0-9]+", text) if t]
    if not tokens:
        return None
    return "_".join(sorted(tokens))


def _is_valid_player_key(key: Any) -> bool:
    if key is None or (isinstance(key, float) and pd.isna(key)):
        return False
    text = str(key).strip().lower()
    return text not in INVALID_PLAYER_KEYS


def prepare_sportradar_matches(fixture_stats: pd.DataFrame) -> pd.DataFrame:
    """One row per sport_event_id with normalized home/away keys + pair_key."""
    required = {
        "sport_event_id",
        "home_competitor_name",
        "away_competitor_name",
        "first_event_time",
    }
    missing = required - set(fixture_stats.columns)
    if missing:
        raise ValueError(f"fixture_stats missing columns: {sorted(missing)}")

    sr = fixture_stats.loc[:, list(required)].copy()
    sr = sr.dropna(subset=["sport_event_id"]).drop_duplicates(subset=["sport_event_id"])
    sr["first_event_time"] = pd.to_datetime(sr["first_event_time"], utc=True, errors="coerce")
    sr["norm_home"] = sr["home_competitor_name"].map(normalize_player_name)
    sr["norm_away"] = sr["away_competitor_name"].map(normalize_player_name)
    sr = sr.dropna(subset=["norm_home", "norm_away", "first_event_time"])
    # Require two distinct players (skip malformed rows)
    sr = sr.loc[sr["norm_home"] != sr["norm_away"]].copy()
    sr["pair_key"] = sr.apply(
        lambda r: "|".join(sorted([r["norm_home"], r["norm_away"]])),
        axis=1,
    )
    return sr.reset_index(drop=True)


def build_oddsjam_fixture_pairs(consensus: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Collapse consensus to one row per fixture_id with exactly two player keys.

    Returns (pairs_df, insufficient_df).
    Prefer moneyline keys; if moneyline has < 2, try all player-level markets.
    """
    required = {"fixture_id", "start_date", "market", "normalized_selection_key"}
    missing = required - set(consensus.columns)
    if missing:
        raise ValueError(f"consensus missing columns: {sorted(missing)}")

    c = consensus.loc[:, list(required)].copy()
    c["start_date"] = pd.to_datetime(c["start_date"], utc=True, errors="coerce")
    c["market_l"] = c["market"].astype("string").str.lower().str.strip()
    c["player_key"] = c["normalized_selection_key"].map(normalize_player_name)
    c = c.loc[c["player_key"].map(_is_valid_player_key)].copy()

    def _keys_for(frame: pd.DataFrame) -> set[str]:
        return set(frame["player_key"].dropna().astype(str))

    rows: list[dict[str, Any]] = []
    insufficient: list[dict[str, Any]] = []

    for fixture_id, grp in c.groupby("fixture_id", sort=False):
        start_date = grp["start_date"].dropna().iloc[0] if grp["start_date"].notna().any() else pd.NaT
        ml_keys = _keys_for(grp.loc[grp["market_l"] == "moneyline"])
        all_keys = _keys_for(grp)

        if len(ml_keys) == 2:
            keys = sorted(ml_keys)
            method = "moneyline"
        elif len(ml_keys) < 2 and len(all_keys) == 2:
            keys = sorted(all_keys)
            method = "all_player_markets"
        else:
            insufficient.append(
                {
                    "fixture_id": fixture_id,
                    "start_date": start_date,
                    "n_moneyline_players": len(ml_keys),
                    "n_all_players": len(all_keys),
                    "reason": "insufficient_players",
                }
            )
            continue

        rows.append(
            {
                "fixture_id": fixture_id,
                "start_date": start_date,
                "oj_player_a": keys[0],
                "oj_player_b": keys[1],
                "pair_key": "|".join(keys),
                "player_source": method,
            }
        )

    pairs = pd.DataFrame(rows)
    insuff = pd.DataFrame(insufficient)
    if not pairs.empty:
        pairs = pairs.dropna(subset=["start_date"]).reset_index(drop=True)
    return pairs, insuff


def match_fixtures(
    sportradar: pd.DataFrame,
    oddsjam_pairs: pd.DataFrame,
    *,
    time_window_hours: float = DEFAULT_TIME_WINDOW_HOURS,
    time_margin_minutes: float = DEFAULT_TIME_MARGIN_MINUTES,
) -> dict[str, pd.DataFrame]:
    """
    Candidate join on pair_key + time window; accept mutual rank-1 with margin.

    Returns dict with accepted, ambiguous, unmatched_sr, candidates.
    """
    if sportradar.empty or oddsjam_pairs.empty:
        return {
            "accepted": pd.DataFrame(),
            "ambiguous": pd.DataFrame(),
            "unmatched_sr": sportradar.copy(),
            "candidates": pd.DataFrame(),
        }

    candidates = sportradar.merge(
        oddsjam_pairs,
        on="pair_key",
        how="inner",
        suffixes=("_sr", "_oj"),
    )
    if candidates.empty:
        return {
            "accepted": pd.DataFrame(),
            "ambiguous": pd.DataFrame(),
            "unmatched_sr": sportradar.copy(),
            "candidates": candidates,
        }

    candidates["time_delta_minutes"] = (
        candidates["first_event_time"] - candidates["start_date"]
    ).dt.total_seconds() / 60.0
    candidates["abs_time_delta_minutes"] = candidates["time_delta_minutes"].abs()
    window_minutes = time_window_hours * 60.0
    candidates = candidates.loc[
        candidates["abs_time_delta_minutes"] <= window_minutes
    ].copy()

    if candidates.empty:
        return {
            "accepted": pd.DataFrame(),
            "ambiguous": pd.DataFrame(),
            "unmatched_sr": sportradar.copy(),
            "candidates": candidates,
        }

    candidates["rank_by_sr"] = (
        candidates.groupby("sport_event_id")["abs_time_delta_minutes"]
        .rank(method="min", ascending=True)
        .astype(int)
    )
    candidates["rank_by_oj"] = (
        candidates.groupby("fixture_id")["abs_time_delta_minutes"]
        .rank(method="min", ascending=True)
        .astype(int)
    )

    # Second-best abs delta per side (for margin rule)
    def _second_best(series: pd.Series) -> float:
        vals = sorted(series.dropna().unique())
        if len(vals) >= 2:
            return float(vals[1])
        return float("nan")

    sr_second = (
        candidates.groupby("sport_event_id")["abs_time_delta_minutes"]
        .agg(_second_best)
        .rename("sr_second_best_abs")
    )
    oj_second = (
        candidates.groupby("fixture_id")["abs_time_delta_minutes"]
        .agg(_second_best)
        .rename("oj_second_best_abs")
    )
    candidates = candidates.merge(sr_second, on="sport_event_id", how="left")
    candidates = candidates.merge(oj_second, on="fixture_id", how="left")

    def _clear_winner(row: pd.Series, second_col: str) -> bool:
        second = row[second_col]
        if pd.isna(second):
            return True
        return float(row["abs_time_delta_minutes"]) + time_margin_minutes < float(second)

    mutual = candidates.loc[
        (candidates["rank_by_sr"] == 1) & (candidates["rank_by_oj"] == 1)
    ].copy()
    mutual["sr_clear"] = mutual.apply(lambda r: _clear_winner(r, "sr_second_best_abs"), axis=1)
    mutual["oj_clear"] = mutual.apply(lambda r: _clear_winner(r, "oj_second_best_abs"), axis=1)
    accepted_mask = mutual["sr_clear"] & mutual["oj_clear"]
    accepted = mutual.loc[accepted_mask].copy()
    ambiguous = pd.concat(
        [
            mutual.loc[~accepted_mask],
            candidates.loc[
                ~((candidates["rank_by_sr"] == 1) & (candidates["rank_by_oj"] == 1))
            ],
        ],
        ignore_index=True,
    )

    # Deduplicate ambiguous display (same pair can appear once)
    if not ambiguous.empty:
        ambiguous = ambiguous.drop_duplicates(
            subset=["sport_event_id", "fixture_id"], keep="first"
        )

    # If mutual rank-1 produced duplicates (ties), drop those IDs from accepted
    if not accepted.empty:
        dup_sr = accepted["sport_event_id"].duplicated(keep=False)
        dup_oj = accepted["fixture_id"].duplicated(keep=False)
        tied = accepted.loc[dup_sr | dup_oj]
        if not tied.empty:
            ambiguous = pd.concat([ambiguous, tied], ignore_index=True)
            accepted = accepted.loc[~(dup_sr | dup_oj)].copy()

    accepted_sr_ids = set(accepted["sport_event_id"]) if not accepted.empty else set()
    unmatched_sr = sportradar.loc[
        ~sportradar["sport_event_id"].isin(accepted_sr_ids)
    ].copy()

    if not accepted.empty:
        accepted["match_method"] = MATCH_METHOD
        accepted["time_delta_minutes"] = accepted["time_delta_minutes"].astype(float)

    return {
        "accepted": accepted.reset_index(drop=True),
        "ambiguous": ambiguous.reset_index(drop=True),
        "unmatched_sr": unmatched_sr.reset_index(drop=True),
        "candidates": candidates.reset_index(drop=True),
    }


def format_accepted_for_upload(accepted: pd.DataFrame) -> pd.DataFrame:
    """Select/order columns for the BQ crosswalk table and stamp updated_at."""
    if accepted.empty:
        cols = [
            "sport_event_id",
            "fixture_id",
            "first_event_time",
            "start_date",
            "time_delta_minutes",
            "home_competitor_name",
            "away_competitor_name",
            "norm_home",
            "norm_away",
            "oj_player_a",
            "oj_player_b",
            "match_method",
            "updated_at",
        ]
        return pd.DataFrame(columns=cols)

    out = accepted.loc[
        :,
        [
            "sport_event_id",
            "fixture_id",
            "first_event_time",
            "start_date",
            "time_delta_minutes",
            "home_competitor_name",
            "away_competitor_name",
            "norm_home",
            "norm_away",
            "oj_player_a",
            "oj_player_b",
            "match_method",
        ],
    ].copy()
    out["updated_at"] = pd.Timestamp.now(tz="UTC")
    return out.reset_index(drop=True)


def assert_one_to_one(accepted: pd.DataFrame) -> None:
    """Raise if sport_event_id or fixture_id is duplicated in accepted links."""
    if accepted.empty:
        return
    for col in ("sport_event_id", "fixture_id"):
        dup = accepted[col].duplicated(keep=False)
        n = int(dup.sum())
        if n > 0:
            sample = accepted.loc[dup, col].astype(str).drop_duplicates().head(10).tolist()
            raise ValueError(
                f"Accepted crosswalk violates 1:1 on {col}: {n} duplicate rows. "
                f"Sample: {sample}"
            )
