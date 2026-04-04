"""
Initial Elo-style ratings (0–100 scale) from ranking points, with shrinkage toward the mean.

Pipeline: concave log transform of points → affine to [elo_init_min, elo_init_max]
→ shrink toward μ → optional clip → elo_init.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd


def _normalize_competitor_id(competitor_id: str) -> str:
    """Strip whitespace; IDs are matched as stable strings (e.g. sr:competitor:...)."""
    return str(competitor_id).strip()


@dataclass
class EloInitConfig:
    """Tunable knobs for initialization and unranked sampling."""

    elo_init_min: float = 30.0
    elo_init_max: float = 90.0
    """Raw mapping band before shrinkage; top of snapshot maps here (below 100 for headroom)."""

    shrink_lambda: float = 0.65
    """Retention of deviation from μ: elo = μ + shrink_lambda * (elo_raw - μ)."""

    shrink_mu: Literal["median", "mean"] = "median"
    """Central value for shrinkage (computed on elo_raw over the passed rankings frame)."""

    p_lo: float | None = None
    """Lower anchor for log scale; default = min(points) in frame (floored at 0)."""

    p_hi: float | None = None
    """Upper anchor; default = max(points) in frame."""

    p_hi_percentile: float | None = None
    """If set (e.g. 99.5), use this percentile for p_hi instead of max (robust to one outlier)."""

    clip_after_shrink: bool = True
    """Clip elo_init to [elo_init_min, elo_init_max] after shrinkage."""

    unranked_mean: float = 25.0
    unranked_std: float = 3.0
    unranked_clip_low: float = 19.0
    unranked_clip_high: float = 31.0

    random_seed: int | None = None

    def make_rng(self) -> np.random.Generator:
        return np.random.default_rng(self.random_seed)


def _resolve_p_bounds(points: pd.Series, cfg: EloInitConfig) -> tuple[float, float]:
    p = points.astype(float)
    p_lo = float(cfg.p_lo) if cfg.p_lo is not None else float(np.maximum(p.min(), 0.0))
    if cfg.p_hi is not None:
        p_hi = float(cfg.p_hi)
    elif cfg.p_hi_percentile is not None:
        p_hi = float(np.percentile(p, cfg.p_hi_percentile))
    else:
        p_hi = float(p.max())
    if p_hi <= p_lo:
        p_hi = p_lo + 1.0
    return p_lo, p_hi


def points_to_unit(points: pd.Series, p_lo: float, p_hi: float) -> pd.Series:
    """Map points to [0, 1] via log1p, linear in log space."""
    denom = np.log1p(p_hi) - np.log1p(p_lo)
    if denom <= 0:
        return pd.Series(0.5, index=points.index)
    u = (np.log1p(points.astype(float).clip(lower=0)) - np.log1p(p_lo)) / denom
    return pd.Series(u, index=points.index).clip(0.0, 1.0)


def unit_to_elo_raw(u: pd.Series, elo_min: float, elo_max: float) -> pd.Series:
    return elo_min + u * (elo_max - elo_min)


def shrink_toward_mean(values: pd.Series, mu: float, shrink_lambda: float) -> pd.Series:
    return mu + shrink_lambda * (values - mu)


def build_initial_elo_table(
    rankings_df: pd.DataFrame,
    *,
    config: EloInitConfig | None = None,
    id_col: str = "competitor_id",
    points_col: str = "points",
    name_col: str | None = "competitor_name",
) -> pd.DataFrame:
    """
    Add intermediate and final Elo columns to a rankings slice.

    Columns added: p_lo_used, p_hi_used, points_score_u, elo_raw, shrink_mu_used,
    elo_after_shrink, elo_init.

    Parameters
    ----------
    rankings_df
        Must contain id_col and points_col. name_col is optional (for display only).
    """
    cfg = config or EloInitConfig()
    df = rankings_df.copy()
    required = {id_col, points_col}
    missing = required - set(df.columns)
    if missing:
        raise KeyError(
            f"Expected columns {id_col!r} and {points_col!r}; missing {missing!r}. "
            f"Columns present: {list(df.columns)}"
        )

    p_lo, p_hi = _resolve_p_bounds(df[points_col], cfg)
    df["p_lo_used"] = p_lo
    df["p_hi_used"] = p_hi
    df["points_score_u"] = points_to_unit(df[points_col], p_lo, p_hi)
    df["elo_raw"] = unit_to_elo_raw(
        df["points_score_u"], cfg.elo_init_min, cfg.elo_init_max
    )
    mu = (
        float(df["elo_raw"].median())
        if cfg.shrink_mu == "median"
        else float(df["elo_raw"].mean())
    )
    df["shrink_mu_used"] = mu
    df["elo_after_shrink"] = shrink_toward_mean(df["elo_raw"], mu, cfg.shrink_lambda)
    df["elo_init"] = df["elo_after_shrink"]
    if cfg.clip_after_shrink:
        df["elo_init"] = df["elo_init"].clip(cfg.elo_init_min, cfg.elo_init_max)
    return df


def sample_unranked_elo_init(
    config: EloInitConfig | None = None,
    rng: np.random.Generator | None = None,
) -> float:
    """Random prior for players not in the rankings table (clipped Gaussian)."""
    cfg = config or EloInitConfig()
    gen = rng if rng is not None else cfg.make_rng()
    x = float(gen.normal(cfg.unranked_mean, cfg.unranked_std))
    return float(np.clip(x, cfg.unranked_clip_low, cfg.unranked_clip_high))


def lookup_points_by_competitor_id(
    rankings_df: pd.DataFrame,
    competitor_id: str,
    *,
    id_col: str = "competitor_id",
    points_col: str = "points",
) -> float | None:
    """Return ranking points for row match on competitor_id (strip-only), else None."""
    key = _normalize_competitor_id(competitor_id)
    ids = rankings_df[id_col].map(_normalize_competitor_id)
    mask = ids == key
    if not mask.any():
        return None
    idx = rankings_df.index[mask][0]
    return float(rankings_df.loc[idx, points_col])


def elo_init_for_competitor_id(
    competitor_id: str,
    initialized_df: pd.DataFrame,
    *,
    config: EloInitConfig | None = None,
    id_col: str = "competitor_id",
    elo_col: str = "elo_init",
    rng: np.random.Generator | None = None,
) -> tuple[float, Literal["ranked", "unranked"]]:
    """
    Return (elo_init, source). Uses initialized_df from build_initial_elo_table;
    if competitor_id missing, draws unranked prior.
    """
    cfg = config or EloInitConfig()
    gen = rng if rng is not None else cfg.make_rng()
    key = _normalize_competitor_id(competitor_id)
    ids = initialized_df[id_col].map(_normalize_competitor_id)
    mask = ids == key
    if mask.any():
        idx = initialized_df.index[mask][0]
        return float(initialized_df.loc[idx, elo_col]), "ranked"
    return sample_unranked_elo_init(cfg, gen), "unranked"


def points_for_competitor_id(
    competitor_id: str,
    rankings_df: pd.DataFrame,
    *,
    id_col: str = "competitor_id",
    points_col: str = "points",
) -> float | None:
    """Points for a competitor_id (pre-elo), for debugging."""
    return lookup_points_by_competitor_id(
        rankings_df, competitor_id, id_col=id_col, points_col=points_col
    )
