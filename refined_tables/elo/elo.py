"""
Incremental Elo updates on a 0–100 scale with winner ceiling dampening and loser floor dampening.

Ceiling-style loser dampening (shrinking losses for high-rated losers) is not implemented.
Effective per-match K is ``k_base * w_match`` where ``w_match`` comes from tournament level.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, MutableMapping

import numpy as np
import pandas as pd

# Tournament level -> weight on K (user mapping). Unknown levels use default_w_match.
TOURNAMENT_WEIGHTS: dict[str, float] = {
    "grand_slam": 4.0,
    "atp_1000": 3.0,
    "wta_1000": 3.0,
    "atp_500": 2.0,
    "wta_500": 2.0,
    "atp_250": 1.0,
    "wta_250": 1.0,
}


def w_match_for_level(
    level: str | float | None,
    *,
    weights: Mapping[str, float] | None = None,
    default: float = 1.0,
) -> float:
    """Return K multiplier for a tournament level string (case-insensitive)."""
    if level is None or (isinstance(level, float) and np.isnan(level)):
        return default
    key = str(level).strip().lower()
    w = TOURNAMENT_WEIGHTS if weights is None else weights
    return float(w.get(key, default))


@dataclass
class EloUpdateConfig:
    """Tuning for one match update (winner / loser deltas)."""

    s: float = 60.0
    """Logistic scale in E_winner = 1 / (1 + 10^((R_l - R_w)/s)). Lower s => stronger favorite."""

    k_base: float = 1.0
    """Base K; effective K per match is ``k_base * w_match``."""

    r_max: float = 100.0
    """Top of ladder for dampening formulas."""

    gamma_win: float = 0.5
    """Winner ceiling dampen: mult = ((r_max - R_w) / r_max) ** gamma_win."""

    use_winner_dampen: bool = True

    use_loser_floor_dampen: bool = True
    """Loser floor dampen: mult = (max(R_l, r_floor_eps) / r_max) ** gamma_floor."""

    gamma_floor: float = 0.5
    r_floor_eps: float = 1.0

    clip_low: float = 0.0
    clip_high: float = 100.0
    """Clip ratings after each match (set equal to disable clipping)."""

    default_w_match: float = 1.0
    """``w_match`` when level is missing or unknown."""

    tournament_weights: dict[str, float] = field(default_factory=lambda: dict(TOURNAMENT_WEIGHTS))


def expected_winner_score(r_w: float, r_l: float, s: float) -> float:
    return 1.0 / (1.0 + 10 ** ((r_l - r_w) / s))


def dampen_ceiling_mult(r: float, r_max: float, gamma: float) -> float:
    r = float(np.clip(r, 0.0, r_max - 1e-9))
    return float(np.maximum(0.0, (r_max - r) / r_max) ** gamma)


def dampen_floor_mult(r: float, r_max: float, gamma: float, eps: float) -> float:
    r = float(np.clip(r, 0.0, r_max))
    num = max(r, eps)
    return float(np.clip(num / r_max, 0.0, 1.0) ** gamma)


def compute_deltas(
    r_w: float,
    r_l: float,
    w_match: float,
    cfg: EloUpdateConfig,
) -> tuple[float, float]:
    """
    Return (delta_winner, delta_loser) for a win by r_w over r_l.

    Loser delta is negative. Ceiling-style loser dampening is not applied.
    """
    k = cfg.k_base * w_match
    e_w = expected_winner_score(r_w, r_l, cfg.s)
    raw_w = k * (1.0 - e_w)
    raw_l = -raw_w

    m_w = dampen_ceiling_mult(r_w, cfg.r_max, cfg.gamma_win) if cfg.use_winner_dampen else 1.0
    m_l = (
        dampen_floor_mult(r_l, cfg.r_max, cfg.gamma_floor, cfg.r_floor_eps)
        if cfg.use_loser_floor_dampen
        else 1.0
    )

    return raw_w * m_w, raw_l * m_l


def clip_rating(x: float, cfg: EloUpdateConfig) -> float:
    return float(np.clip(x, cfg.clip_low, cfg.clip_high))


def update_pair(
    r_w: float,
    r_l: float,
    w_match: float,
    cfg: EloUpdateConfig,
) -> tuple[float, float]:
    """Apply one match; return (new_r_winner, new_r_loser)."""
    d_w, d_l = compute_deltas(r_w, r_l, w_match, cfg)
    return clip_rating(r_w + d_w, cfg), clip_rating(r_l + d_l, cfg)


def process_matches(
    matches: pd.DataFrame,
    ratings: MutableMapping[str, float],
    *,
    config: EloUpdateConfig | None = None,
    winner_col: str = "winner_id",
    loser_col: str = "loser_id",
    level_col: str = "tournament_level",
    sort_by: str | None = "start_time",
    event_id_col: str = "sport_event_id",
    winner_name_col: str = "winner_name",
    loser_name_col: str = "loser_name",
    w_match_fn: Callable[[Any], float] | None = None,
    return_history: bool = False,
) -> pd.DataFrame | None:
    """
    Walk matches in time order and update ``ratings`` in place.

    Parameters
    ----------
    matches
        Must include winner and loser ids and a tournament level column (unless ``w_match_fn``).
    ratings
        Maps competitor_id -> current Elo. Missing ids default to ``config.clip_low`` (typically 0)
        or can be pre-seeded from initialization.
    config
        Defaults to ``EloUpdateConfig()``.
    w_match_fn
        If set, called per row with the row Series and must return ``w_match`` (ignores ``level_col``).

    Returns
    -------
    If ``return_history`` is True, a DataFrame with one row per match (deltas, new elos, etc.);
    otherwise None.
    """
    cfg = config or EloUpdateConfig()
    df = matches.copy()
    if sort_by is not None and sort_by in df.columns:
        df = df.sort_values(sort_by, ascending=True, kind="mergesort")

    def default_rating(cid: str) -> float:
        return float(ratings[cid]) if cid in ratings else cfg.clip_low

    rows_out: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        w_id = row[winner_col]
        l_id = row[loser_col]
        event_id = row[event_id_col]
        w_name = row[winner_name_col]
        l_name = row[loser_name_col]
        if pd.isna(w_id) or pd.isna(l_id) or w_id == l_id:
            continue

        w_id_s, l_id_s = str(w_id).strip(), str(l_id).strip()

        if w_match_fn is not None:
            w_m = float(w_match_fn(row))
        else:
            w_m = w_match_for_level(
                row[level_col] if level_col in row.index else None,
                weights=cfg.tournament_weights,
                default=cfg.default_w_match,
            )

        r_w = default_rating(w_id_s)
        r_l = default_rating(l_id_s)

        d_w, d_l = compute_deltas(r_w, r_l, w_m, cfg)
        new_w = clip_rating(r_w + d_w, cfg)
        new_l = clip_rating(r_l + d_l, cfg)

        ratings[w_id_s] = new_w
        ratings[l_id_s] = new_l

        if return_history:
            rows_out.append(
                {
                    "event_id": event_id,
                    winner_name_col: w_name,
                    loser_name_col: l_name,
                    winner_col: w_id_s,
                    loser_col: l_id_s,
                    "w_match": w_m,
                    "r_w_before": r_w,
                    "r_l_before": r_l,
                    "delta_w": d_w,
                    "delta_l": d_l,
                    "r_w_after": new_w,
                    "r_l_after": new_l,
                }
            )

    if return_history:
        return pd.DataFrame(rows_out)
    return None
