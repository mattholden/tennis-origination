"""
Initial Elo-style ratings (0–100 scale) from ranking points, with shrinkage toward the mean.

**Ranked** (``build_initial_elo_table``): log1p(points) scaled to a unit in [0,1] using
p_lo/p_hi from the snapshot → affine to ``elo_raw`` in [elo_init_min, elo_init_max] →
shrink toward median/mean → ``elo_init``; optional clip to [elo_init_min, elo_init_max]
after shrinkage (``clip_after_shrink``).

**Unranked** (``sample_unranked_elo_init``): single draw from
``N(unranked_mean, unranked_std)``; optional clip to [unranked_clip_low, unranked_clip_high]
(``unranked_clip_after_sample``). No log mapping and no shrinkage—separate from the ranked path.
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

    unranked_mean: float = 31.0
    unranked_std: float = 3.0
    unranked_clip_low: float = 21.0
    unranked_clip_high: float = 33.0
    unranked_clip_after_sample: bool = False
    """If True, clip unranked draws to [unranked_clip_low, unranked_clip_high] (boundary spikes in histograms)."""

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
    """Random prior for players not in the rankings table: Gaussian unless clipping is enabled."""
    cfg = config or EloInitConfig()
    gen = rng if rng is not None else cfg.make_rng()
    x = float(gen.normal(cfg.unranked_mean, cfg.unranked_std))
    if cfg.unranked_clip_after_sample:
        return float(np.clip(x, cfg.unranked_clip_low, cfg.unranked_clip_high))
    return x


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


def competitors_with_elo_init(
    competitors_df: pd.DataFrame,
    initialized_rankings_df: pd.DataFrame,
    *,
    config: EloInitConfig | None = None,
    competitor_id_col: str = "competitor_id",
    id_col: str = "competitor_id",
    rng: np.random.Generator | None = None,
    include_ranking_columns: bool = True,
) -> pd.DataFrame:
    """
    Left-join all competitors to the output of ``build_initial_elo_table``.

    Ranked players get ``elo_init`` (and optional ranking detail columns) from the snapshot.
    Missing IDs get the same unranked prior as ``sample_unranked_elo_init`` / ``elo_init_for_competitor_id``,
    using sequential draws from ``rng`` (or ``config.make_rng()``).

    Adds ``elo_init_source``: ``\"ranked\"`` or ``\"unranked\"``. Ranking ``points`` is merged as
    ``ranking_points`` to avoid clashing with any ``points`` column on the competitors frame.
    """
    cfg = config or EloInitConfig()
    gen = rng if rng is not None else cfg.make_rng()

    rank = initialized_rankings_df.copy()
    if "elo_init" not in rank.columns:
        raise KeyError(
            "initialized_rankings_df must include 'elo_init' (output of build_initial_elo_table)"
        )
    rank["_elo_join"] = rank[id_col].map(_normalize_competitor_id)
    rank = rank.drop_duplicates(subset="_elo_join", keep="first")

    detail = (
        "points",
        "p_lo_used",
        "p_hi_used",
        "points_score_u",
        "elo_raw",
        "shrink_mu_used",
        "elo_after_shrink",
        "elo_init",
    )
    if not include_ranking_columns:
        cols = ["_elo_join", "elo_init"]
    else:
        cols = ["_elo_join"] + [c for c in detail if c in rank.columns]

    right = rank[cols].copy()
    if "points" in right.columns:
        right = right.rename(columns={"points": "ranking_points"})

    out = competitors_df.copy()
    out["_elo_join"] = out[competitor_id_col].map(_normalize_competitor_id)
    merged = out.merge(right, on="_elo_join", how="left")
    merged = merged.drop(columns=["_elo_join"])

    unranked = merged["elo_init"].isna()
    n = int(unranked.sum())
    if n:
        merged.loc[unranked, "elo_init"] = [
            sample_unranked_elo_init(cfg, gen) for _ in range(n)
        ]

    merged["elo_init_source"] = np.where(unranked, "unranked", "ranked")
    return merged
