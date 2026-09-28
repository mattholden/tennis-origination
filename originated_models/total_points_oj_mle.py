"""
Games-only Gaussian MLE helpers for total-games → total-points modeling.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.model_selection import train_test_split

P_MORE_GRID = np.arange(0.05, 1.00, 0.05)
_NORMAL = NormalDist(mu=0.0, sigma=1.0)


@dataclass(frozen=True)
class GamesOnlyGaussianMLE:
    """
    mu(g) = beta0 + beta1 * g
    log(sigma^2) = gamma0 + gamma1 * scaled(g_var)

    In the hybrid fit, beta is estimated on actual games while gamma / games_mean /
    games_std are estimated on residuals around mu(projected games), indexed by
    projected games. At score time pass projected games to both predict_mean and
    predict_sigma.
    """

    beta: np.ndarray
    gamma: np.ndarray
    games_mean: float
    games_std: float
    n_obs: int

    @property
    def intercept(self) -> float:
        return float(self.beta[0])

    @property
    def slope(self) -> float:
        return float(self.beta[1])

    def predict_mean(self, games: np.ndarray) -> np.ndarray:
        g = np.asarray(games, dtype=float)
        return self.beta[0] + self.beta[1] * g

    def predict_sigma(self, games: np.ndarray) -> np.ndarray:
        g = np.asarray(games, dtype=float)
        g_scaled = (g - self.games_mean) / self.games_std
        log_var = self.gamma[0] + self.gamma[1] * g_scaled
        return np.clip(np.sqrt(np.exp(log_var)), 1e-6, None)


def fit_gaussian_mean_mle(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Fit Gaussian mean via MLE with homoskedastic log-sigma nuisance param."""
    n = X.shape[0]
    xd = np.column_stack([np.ones(n), X])

    beta_init = np.linalg.lstsq(xd, y, rcond=None)[0]
    resid_init = y - xd @ beta_init
    sigma_init = max(float(np.std(resid_init, ddof=1)), 1e-3)
    theta0 = np.concatenate([beta_init, np.array([np.log(sigma_init)])])

    def nll(theta: np.ndarray) -> float:
        beta = theta[:-1]
        log_sigma = float(theta[-1])
        sigma2 = np.exp(2.0 * log_sigma)
        resid = y - xd @ beta
        return float(0.5 * np.sum(np.log(2.0 * np.pi * sigma2) + (resid**2) / sigma2))

    res = minimize(nll, theta0, method="L-BFGS-B")
    theta_hat = res.x if res.success else theta0
    return theta_hat[:-1]


def fit_variance_mle_from_residuals(
    games: np.ndarray, residuals: np.ndarray
) -> tuple[np.ndarray, float, float]:
    """Fit log(sigma^2) = gamma0 + gamma1 * scaled_games via MLE on residuals."""
    g = games.astype(float)
    g_mean = float(np.mean(g))
    g_std = float(np.std(g, ddof=0))
    if g_std <= 0:
        g_std = 1.0
    g_scaled = (g - g_mean) / g_std

    z = np.column_stack([np.ones(len(g_scaled)), g_scaled])
    eps = 1e-6
    gamma_init = np.linalg.lstsq(z, np.log(residuals**2 + eps), rcond=None)[0]

    def nll(gamma: np.ndarray) -> float:
        log_var = z @ gamma
        var = np.exp(log_var)
        return float(0.5 * np.sum(np.log(2.0 * np.pi * var) + (residuals**2) / var))

    res = minimize(nll, gamma_init, method="L-BFGS-B")
    gamma_hat = res.x if res.success else gamma_init
    return gamma_hat, g_mean, g_std


def fit_hybrid_games_gaussian_mle(
    mean_games: np.ndarray,
    variance_games: np.ndarray,
    total_points: np.ndarray,
) -> GamesOnlyGaussianMLE:
    """
    Hybrid games-only Gaussian MLE:

    - Fit mu on ``mean_games`` (typically actual total_games_played)
    - Residuals = y - mu(variance_games) (typically OddsJam projected line)
    - Fit heteroskedastic sigma on those residuals vs ``variance_games``
    """
    g_mean = np.asarray(mean_games, dtype=float)
    g_var = np.asarray(variance_games, dtype=float)
    y = np.asarray(total_points, dtype=float)
    if not (len(g_mean) == len(g_var) == len(y)):
        raise ValueError(
            f"mean_games, variance_games, total_points length mismatch: "
            f"{len(g_mean)}, {len(g_var)}, {len(y)}"
        )
    if len(y) < 5:
        raise ValueError(f"Need at least 5 observations to fit MLE, got {len(y)}")

    beta = fit_gaussian_mean_mle(g_mean.reshape(-1, 1), y)
    mu_at_var_games = beta[0] + beta[1] * g_var
    resid = y - mu_at_var_games
    gamma, g_center, g_scale = fit_variance_mle_from_residuals(g_var, resid)
    return GamesOnlyGaussianMLE(
        beta=beta,
        gamma=gamma,
        games_mean=g_center,
        games_std=g_scale,
        n_obs=len(y),
    )


def fit_games_only_gaussian_mle(games: np.ndarray, total_points: np.ndarray) -> GamesOnlyGaussianMLE:
    """Fit mean + variance on the same games feature (non-hybrid)."""
    g = np.asarray(games, dtype=float)
    return fit_hybrid_games_gaussian_mle(g, g, total_points)


def quantile_edges(series: pd.Series, n_bins: int) -> np.ndarray:
    vals = pd.to_numeric(series, errors="coerce").dropna().to_numpy(dtype=float)
    if len(vals) == 0:
        return np.array([0.0, 1.0])
    probs = np.linspace(0.0, 1.0, n_bins + 1)
    edges = np.unique(np.quantile(vals, probs))
    if len(edges) < 2:
        v = float(vals[0])
        edges = np.array([v - 0.5, v + 0.5])
    return edges


def summarize_curve(samples_2d: np.ndarray) -> dict[str, np.ndarray]:
    return {
        "p10": np.nanpercentile(samples_2d, 10, axis=0),
        "p50": np.nanpercentile(samples_2d, 50, axis=0),
        "p90": np.nanpercentile(samples_2d, 90, axis=0),
    }


def _level_label(category: object, level: object) -> str:
    cat = "unknown" if pd.isna(category) else str(category).strip()
    lvl = "unknown" if pd.isna(level) else str(level).strip()
    return f"{cat} | {lvl}"


def _games_line_exceedance_by_label(
    df: pd.DataFrame,
    labels: pd.Series,
    *,
    actual_games_col: str = "total_games_played",
    projected_games_col: str = "projected_total_games",
) -> pd.DataFrame:
    """
    P(actual games > consensus projected games) by arbitrary row labels.

    Rows missing either games column are dropped before aggregation.
    """
    if len(df) != len(labels):
        raise ValueError("labels must align with df rows")
    work = df.copy()
    work["_label"] = pd.Series(labels).astype(str).to_numpy()
    actual = pd.to_numeric(work[actual_games_col], errors="coerce")
    projected = pd.to_numeric(work[projected_games_col], errors="coerce")
    valid = actual.notna() & projected.notna()
    work = work.loc[valid].copy()
    if work.empty:
        return pd.DataFrame(
            columns=["level_label", "games_line_exceedance", "n_games_line"]
        )
    work["_above_games"] = (
        actual.loc[valid].to_numpy(dtype=float) > projected.loc[valid].to_numpy(dtype=float)
    ).astype(float)
    return (
        work.groupby("_label", dropna=False)
        .agg(
            games_line_exceedance=("_above_games", "mean"),
            n_games_line=("_above_games", "size"),
        )
        .reset_index()
        .rename(columns={"_label": "level_label"})
    )


def _attach_games_line_exceedance(
    summary: pd.DataFrame,
    games_rates: pd.DataFrame,
) -> pd.DataFrame:
    cols = ["level_label", "games_line_exceedance"]
    if "n_games_line" in games_rates.columns:
        cols.append("n_games_line")
    out = summary.merge(games_rates[cols], on="level_label", how="left")
    if "n_games_line" in out.columns:
        out["n_games_line"] = out["n_games_line"].fillna(0).astype(int)
    return out


def _full_dataset_games_line_panels(
    data: pd.DataFrame,
    *,
    category_col: str,
    level_col: str,
    gender_col: str,
    best_of_col: str,
    actual_games_col: str,
    score_games_col: str,
) -> dict[str, pd.DataFrame]:
    """
    Games-line exceedance on the full (unsplit) match set for bootstrap plot markers.

    Returns level / gender-bo3 / ATP-GS rate tables keyed like the bootstrap summaries.
    """
    work = data.copy()
    work["_level"] = [
        _level_label(c, lv)
        for c, lv in zip(work[category_col], work[level_col], strict=True)
    ]
    level_rates = _games_line_exceedance_by_label(
        work,
        work["_level"],
        actual_games_col=actual_games_col,
        projected_games_col=score_games_col,
    )
    bo3 = work.loc[pd.to_numeric(work[best_of_col], errors="coerce") == 3].copy()
    gender_rates = _games_line_exceedance_by_label(
        bo3,
        pd.Series([_gender_bo3_label(v) for v in bo3[gender_col]], index=bo3.index),
        actual_games_col=actual_games_col,
        projected_games_col=score_games_col,
    )
    gs = work.loc[work["_level"] == ATP_GS_LEVEL_LABEL].copy()
    gs_rates = _games_line_exceedance_by_label(
        gs,
        gs["_level"],
        actual_games_col=actual_games_col,
        projected_games_col=score_games_col,
    )
    return {
        "level": level_rates,
        "gender": gender_rates,
        "atp_gs": gs_rates,
    }


def evaluate_pmore_half_by_level(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    fits_by_best_of: dict[int, GamesOnlyGaussianMLE],
    *,
    category_col: str = "category_name",
    level_col: str = "competition_level",
    season_col: str = "season_id",
    score_games_col: str = "projected_total_games",
    points_col: str = "total_points",
    best_of_col: str = "mode_best_of",
    actual_games_col: str = "total_games_played",
) -> tuple[pd.DataFrame, list[str]]:
    """
    Empirical exceedance at p-more=0.5 (actual > mu) by category × competition level.

    Scores the tournament **test** holdout with hybrid fits keyed by mode_best_of.
    Train/test tournament and match counts are included for labels. Levels present
    in train but with no scorable test rows are returned as warning strings.

    Also attaches ``games_line_exceedance`` = P(actual games > OJ projected games)
    on the same test holdout rows.
    """
    for col in (
        category_col,
        level_col,
        season_col,
        score_games_col,
        points_col,
        best_of_col,
        actual_games_col,
    ):
        if col not in train_df.columns and col in (category_col, level_col, season_col):
            raise KeyError(f"train_df missing required column: {col}")
        if col not in test_df.columns:
            raise KeyError(f"test_df missing required column: {col}")

    tr = train_df.copy()
    te = test_df.dropna(subset=[score_games_col, points_col, best_of_col]).copy()

    for frame in (tr, te):
        frame["_level"] = [
            _level_label(c, lv)
            for c, lv in zip(frame[category_col], frame[level_col], strict=True)
        ]

    train_counts = (
        tr.groupby("_level", dropna=False)
        .agg(
            n_train_tournaments=(season_col, "nunique"),
            n_train_matches=(season_col, "size"),
        )
        .reset_index()
    )
    test_counts = (
        te.groupby("_level", dropna=False)
        .agg(
            n_test_tournaments=(season_col, "nunique"),
            n_test_matches=(season_col, "size"),
        )
        .reset_index()
    )

    # Score each test match with the bo3/bo5 fit trained for that format.
    g = pd.to_numeric(te[score_games_col], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(te[points_col], errors="coerce").to_numpy(dtype=float)
    bo = pd.to_numeric(te[best_of_col], errors="coerce").to_numpy(dtype=float)
    mu = np.full(len(te), np.nan)
    for bo_key, fit in fits_by_best_of.items():
        mask = np.isfinite(g) & np.isfinite(y) & (bo == float(bo_key))
        if not mask.any():
            continue
        mu[mask] = fit.predict_mean(g[mask])

    te = te.copy()
    te["_mu"] = mu
    te["_above"] = np.where(np.isfinite(mu), (y > mu).astype(float), np.nan)
    scored = te.loc[np.isfinite(te["_mu"])].copy()

    exceed = (
        scored.groupby("_level", dropna=False)
        .agg(
            empirical_exceedance=("_above", "mean"),
            n_test_scored=("_above", "size"),
        )
        .reset_index()
    )
    games_line = _games_line_exceedance_by_label(
        te,
        te["_level"],
        actual_games_col=actual_games_col,
        projected_games_col=score_games_col,
    )

    summary = train_counts.merge(test_counts, on="_level", how="outer").merge(
        exceed, on="_level", how="outer"
    )
    for col in (
        "n_train_tournaments",
        "n_train_matches",
        "n_test_tournaments",
        "n_test_matches",
        "n_test_scored",
    ):
        summary[col] = summary[col].fillna(0).astype(int)
    summary = summary.rename(columns={"_level": "level_label"})
    summary = _attach_games_line_exceedance(summary, games_line)
    summary = summary.sort_values(
        ["empirical_exceedance", "level_label"], ascending=[False, True], na_position="last"
    ).reset_index(drop=True)

    empty_msgs: list[str] = []
    for _, row in summary.iterrows():
        label = str(row["level_label"])
        if int(row["n_test_scored"]) == 0:
            empty_msgs.append(
                f"{label}: no scorable test matches "
                f"(train {int(row['n_train_tournaments'])} tournaments / "
                f"{int(row['n_train_matches'])} matches; "
                f"test {int(row['n_test_tournaments'])} tournaments / "
                f"{int(row['n_test_matches'])} matches)"
            )

    return summary, empty_msgs


def evaluate_holdout_pmore_half_by_gender(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    *,
    category_col: str = "category_name",
    level_col: str = "competition_level",
    gender_col: str = "competition_gender",
    season_col: str = "season_id",
    score_games_col: str = "projected_total_games",
    points_col: str = "total_points",
    best_of_col: str = "mode_best_of",
    actual_games_col: str = "total_games_played",
) -> dict[str, Any]:
    """
    Single tournament holdout evaluation with separate men/women hybrid fits.

    Fits (men, bo3), (men, bo5), (women, bo3) on train; scores test with the
    matching segment model. Returns level / men-vs-women / ATP-GS summaries
    in the same shape used by the holdout stacked plots.
    """
    for col in (
        category_col,
        level_col,
        gender_col,
        season_col,
        score_games_col,
        points_col,
        best_of_col,
        actual_games_col,
    ):
        if col not in train_df.columns:
            raise KeyError(f"train_df missing required column: {col}")
        if col not in test_df.columns:
            raise KeyError(f"test_df missing required column: {col}")

    fits = _fit_hybrid_by_gender_best_of(
        train_df,
        gender_col=gender_col,
        score_games_col=score_games_col,
        points_col=points_col,
        best_of_col=best_of_col,
        actual_games_col=actual_games_col,
    )
    if not fits:
        raise ValueError("Could not fit any men/women hybrid segments on train.")

    scored = _score_above_mu_by_gender_best_of(
        test_df,
        fits,
        gender_col=gender_col,
        score_games_col=score_games_col,
        points_col=points_col,
        best_of_col=best_of_col,
    )
    if scored.empty:
        raise ValueError("No scorable test rows after men/women segment scoring.")

    tr = train_df.copy()
    te = test_df.copy()
    for frame in (tr, te, scored):
        frame["_level"] = [
            _level_label(c, lv)
            for c, lv in zip(frame[category_col], frame[level_col], strict=True)
        ]

    def _counts(df: pd.DataFrame, label_col: str, prefix: str) -> pd.DataFrame:
        return (
            df.groupby(label_col, dropna=False)
            .agg(
                **{
                    f"n_{prefix}_tournaments": (season_col, "nunique"),
                    f"n_{prefix}_matches": (season_col, "size"),
                }
            )
            .reset_index()
            .rename(columns={label_col: "level_label"})
        )

    train_level = _counts(tr, "_level", "train")
    test_level = _counts(te, "_level", "test")
    exceed_level = (
        scored.groupby("_level", dropna=False)
        .agg(
            empirical_exceedance=("_above", "mean"),
            n_test_scored=("_above", "size"),
        )
        .reset_index()
        .rename(columns={"_level": "level_label"})
    )
    level_summary = train_level.merge(test_level, on="level_label", how="outer").merge(
        exceed_level, on="level_label", how="outer"
    )
    for col in (
        "n_train_tournaments",
        "n_train_matches",
        "n_test_tournaments",
        "n_test_matches",
        "n_test_scored",
    ):
        level_summary[col] = level_summary[col].fillna(0).astype(int)
    level_summary = _attach_games_line_exceedance(
        level_summary,
        _games_line_exceedance_by_label(
            te,
            te["_level"],
            actual_games_col=actual_games_col,
            projected_games_col=score_games_col,
        ),
    )

    # Men vs women aggregates (bo3 only).
    tr_bo3 = tr.loc[pd.to_numeric(tr[best_of_col], errors="coerce") == 3].copy()
    te_bo3 = te.loc[pd.to_numeric(te[best_of_col], errors="coerce") == 3].copy()
    scored_bo3 = scored.loc[pd.to_numeric(scored[best_of_col], errors="coerce") == 3].copy()
    for frame in (tr_bo3, te_bo3, scored_bo3):
        frame["_gender_level"] = [_gender_bo3_label(v) for v in frame[gender_col]]

    train_sex = _counts(tr_bo3, "_gender_level", "train")
    test_sex = _counts(te_bo3, "_gender_level", "test")
    exceed_sex = (
        scored_bo3.groupby("_gender_level", dropna=False)
        .agg(
            empirical_exceedance=("_above", "mean"),
            n_test_scored=("_above", "size"),
        )
        .reset_index()
        .rename(columns={"_gender_level": "level_label"})
    )
    sex_summary = train_sex.merge(test_sex, on="level_label", how="outer").merge(
        exceed_sex, on="level_label", how="outer"
    )
    for col in (
        "n_train_tournaments",
        "n_train_matches",
        "n_test_tournaments",
        "n_test_matches",
        "n_test_scored",
    ):
        sex_summary[col] = sex_summary[col].fillna(0).astype(int)
    sex_summary = _attach_games_line_exceedance(
        sex_summary,
        _games_line_exceedance_by_label(
            te_bo3,
            te_bo3["_gender_level"],
            actual_games_col=actual_games_col,
            projected_games_col=score_games_col,
        ),
    )
    sex_order = {"Men | best_of_3": 0, "Women | best_of_3": 1}
    sex_summary["_ord"] = sex_summary["level_label"].map(sex_order).fillna(99)
    sex_summary = (
        sex_summary.sort_values(["_ord", "level_label"], ascending=[False, False])
        .drop(columns=["_ord"])
        .reset_index(drop=True)
    )

    # ATP GS (men bo5 rows).
    gs_mask_scored = (scored["_level"] == ATP_GS_LEVEL_LABEL) & (
        pd.to_numeric(scored[best_of_col], errors="coerce") == 5
    )
    gs_scored = scored.loc[gs_mask_scored].copy()
    tr_gs = tr.loc[tr["_level"] == ATP_GS_LEVEL_LABEL]
    te_gs = te.loc[te["_level"] == ATP_GS_LEVEL_LABEL]
    gs_games = _games_line_exceedance_by_label(
        te_gs,
        te_gs["_level"],
        actual_games_col=actual_games_col,
        projected_games_col=score_games_col,
    )
    gs_games_rate = (
        float(gs_games["games_line_exceedance"].iloc[0]) if len(gs_games) else np.nan
    )
    gs_games_n = int(gs_games["n_games_line"].iloc[0]) if len(gs_games) else 0
    if gs_scored.empty:
        gs_summary = pd.DataFrame(
            [
                {
                    "level_label": ATP_GS_LEVEL_LABEL,
                    "n_train_tournaments": int(tr_gs[season_col].nunique()),
                    "n_train_matches": int(len(tr_gs)),
                    "n_test_tournaments": int(te_gs[season_col].nunique()),
                    "n_test_matches": int(len(te_gs)),
                    "empirical_exceedance": np.nan,
                    "n_test_scored": 0,
                    "games_line_exceedance": gs_games_rate,
                    "n_games_line": gs_games_n,
                }
            ]
        )
    else:
        gs_summary = pd.DataFrame(
            [
                {
                    "level_label": ATP_GS_LEVEL_LABEL,
                    "n_train_tournaments": int(tr_gs[season_col].nunique()),
                    "n_train_matches": int(len(tr_gs)),
                    "n_test_tournaments": int(te_gs[season_col].nunique()),
                    "n_test_matches": int(len(te_gs)),
                    "empirical_exceedance": float(gs_scored["_above"].mean()),
                    "n_test_scored": int(len(gs_scored)),
                    "games_line_exceedance": gs_games_rate,
                    "n_games_line": gs_games_n,
                }
            ]
        )

    level_summary = level_summary.sort_values("level_label", ascending=False).reset_index(
        drop=True
    )
    return {
        "fits": fits,
        "level_summary": level_summary,
        "sex_summary": sex_summary,
        "atp_gs_summary": gs_summary,
        "fit_keys": sorted(f"{g}_bo{bo}" for g, bo in fits),
    }


def evaluate_pmore_half_by_gender_bo3(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    fit_bo3: GamesOnlyGaussianMLE,
    *,
    gender_col: str = "competition_gender",
    season_col: str = "season_id",
    score_games_col: str = "projected_total_games",
    points_col: str = "total_points",
    best_of_col: str = "mode_best_of",
    actual_games_col: str = "total_games_played",
) -> pd.DataFrame:
    """
    Empirical exceedance at p-more=0.5 for best-of-3 matches, aggregated by gender.

    Uses only ``mode_best_of == 3`` rows and scores with the bo3 hybrid fit.
    Attaches test-set ``games_line_exceedance`` (actual games > OJ projected games).
    """
    for col in (
        gender_col,
        season_col,
        score_games_col,
        points_col,
        best_of_col,
        actual_games_col,
    ):
        if col not in train_df.columns:
            raise KeyError(f"train_df missing required column: {col}")
        if col not in test_df.columns:
            raise KeyError(f"test_df missing required column: {col}")

    def _bo3_frame(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        bo = pd.to_numeric(out[best_of_col], errors="coerce")
        return out.loc[bo == 3].copy()

    tr = _bo3_frame(train_df)
    te = _bo3_frame(test_df).dropna(subset=[score_games_col, points_col, gender_col])

    def _gender_label(val: object) -> str:
        if pd.isna(val):
            return "unknown"
        s = str(val).strip().lower()
        if s in {"men", "man", "male", "m"}:
            return "Men | best_of_3"
        if s in {"women", "woman", "female", "w"}:
            return "Women | best_of_3"
        return f"{s} | best_of_3"

    tr["_level"] = [_gender_label(v) for v in tr[gender_col]]
    te["_level"] = [_gender_label(v) for v in te[gender_col]]

    train_counts = (
        tr.groupby("_level", dropna=False)
        .agg(
            n_train_tournaments=(season_col, "nunique"),
            n_train_matches=(season_col, "size"),
        )
        .reset_index()
    )
    test_counts = (
        te.groupby("_level", dropna=False)
        .agg(
            n_test_tournaments=(season_col, "nunique"),
            n_test_matches=(season_col, "size"),
        )
        .reset_index()
    )

    g = pd.to_numeric(te[score_games_col], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(te[points_col], errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(g) & np.isfinite(y)
    mu = np.full(len(te), np.nan)
    if mask.any():
        mu[mask] = fit_bo3.predict_mean(g[mask])
    te = te.copy()
    te["_mu"] = mu
    te["_above"] = np.where(np.isfinite(mu), (y > mu).astype(float), np.nan)
    scored = te.loc[np.isfinite(te["_mu"])].copy()

    exceed = (
        scored.groupby("_level", dropna=False)
        .agg(
            empirical_exceedance=("_above", "mean"),
            n_test_scored=("_above", "size"),
        )
        .reset_index()
    )

    summary = train_counts.merge(test_counts, on="_level", how="outer").merge(
        exceed, on="_level", how="outer"
    )
    for col in (
        "n_train_tournaments",
        "n_train_matches",
        "n_test_tournaments",
        "n_test_matches",
        "n_test_scored",
    ):
        summary[col] = summary[col].fillna(0).astype(int)
    summary = summary.rename(columns={"_level": "level_label"})
    summary = _attach_games_line_exceedance(
        summary,
        _games_line_exceedance_by_label(
            te,
            te["_level"],
            actual_games_col=actual_games_col,
            projected_games_col=score_games_col,
        ),
    )

    order = {"Men | best_of_3": 0, "Women | best_of_3": 1}
    summary["_ord"] = summary["level_label"].map(order).fillna(99)
    summary = summary.sort_values(["_ord", "level_label"]).drop(columns=["_ord"]).reset_index(drop=True)
    return summary


def score_games_only_mle_calibration(
    fit: GamesOnlyGaussianMLE,
    score_games: np.ndarray,
    total_points: np.ndarray,
    *,
    n_bins: int = 10,
    p_more_grid: np.ndarray | None = None,
) -> dict[str, Any]:
    """
    Single holdout calibration for a fitted games-only / hybrid MLE.

    Scores ``score_games`` (typically OddsJam projected games) against
    ``total_points``. No resampling — intended for the tournament test split.
    """
    p_grid = P_MORE_GRID if p_more_grid is None else np.asarray(p_more_grid, dtype=float)
    g = np.asarray(score_games, dtype=float)
    y = np.asarray(total_points, dtype=float)
    mask = np.isfinite(g) & np.isfinite(y)
    g, y = g[mask], y[mask]
    if len(y) < 5:
        raise ValueError(f"Need at least 5 test rows for calibration, got {len(y)}")

    mu = fit.predict_mean(g)
    sigma = fit.predict_sigma(g)

    curve_b = np.asarray(
        [
            float(np.mean(y > (mu + sigma * _NORMAL.inv_cdf(1.0 - float(p_more)))))
            for p_more in p_grid
        ],
        dtype=float,
    )

    pred_edges = quantile_edges(pd.Series(mu), n_bins=n_bins)
    test_df = pd.DataFrame({"pred": mu, "actual": y})
    test_df["bin_id"] = pd.cut(
        test_df["pred"], bins=pred_edges, include_lowest=True, labels=False
    )
    test_df["above"] = (test_df["actual"] > test_df["pred"]).astype(float)
    grouped = (
        test_df.groupby("bin_id", dropna=False)
        .agg(pct=("above", "mean"), n=("above", "size"), pred_mid=("pred", "mean"))
    )

    n_pred_bins = len(pred_edges) - 1
    curve_c_x = np.full(n_pred_bins, np.nan)
    curve_c = np.full(n_pred_bins, np.nan)
    curve_c_count = np.zeros(n_pred_bins)
    for b in range(n_pred_bins):
        if b in grouped.index and pd.notna(grouped.loc[b, "pct"]):
            curve_c_x[b] = float(grouped.loc[b, "pred_mid"])
            curve_c[b] = float(grouped.loc[b, "pct"])
            curve_c_count[b] = float(grouped.loc[b, "n"])

    return {
        "p_more_grid": p_grid,
        "curve_b": curve_b,
        "curve_c_x": curve_c_x,
        "curve_c": curve_c,
        "curve_c_count": curve_c_count,
        "n_test": int(len(y)),
        "n_train_fit": int(fit.n_obs),
    }


def run_games_only_mle_calibration(
    df_seg: pd.DataFrame,
    *,
    fit_games_col: str = "total_games_played",
    score_games_col: str | None = None,
    games_col: str | None = None,
    points_col: str = "total_points",
    n_bins: int = 10,
    n_repeats: int = 200,
    test_size: float = 0.30,
    p_more_grid: np.ndarray | None = None,
    hybrid: bool = True,
) -> dict[str, Any]:
    """
    Repeated 70/30 calibration for games-only heteroskedastic Gaussian MLE.

    Default hybrid=True:
      - Fit mu on ``fit_games_col`` (actual games)
      - Fit sigma on residuals y - mu(score_games), vs ``score_games_col``
      - Score held-out fold with mu/sigma at ``score_games_col``

    Calibration B: empirical exceedance vs target p-more (uses sigma(g)).
    Calibration C: P(actual > mu) by quantile bins of predicted total points.
    """
    # Backward-compatible alias used by earlier notebook cells.
    if games_col is not None:
        fit_games_col = games_col
        if score_games_col is None:
            score_games_col = games_col
    if score_games_col is None:
        score_games_col = fit_games_col

    p_grid = P_MORE_GRID if p_more_grid is None else np.asarray(p_more_grid, dtype=float)
    needed = [fit_games_col, score_games_col, points_col]
    data = df_seg.dropna(subset=needed).copy()
    g_fit = pd.to_numeric(data[fit_games_col], errors="coerce").to_numpy(dtype=float)
    g_score = pd.to_numeric(data[score_games_col], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(data[points_col], errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(g_fit) & np.isfinite(g_score) & np.isfinite(y)
    g_fit, g_score, y = g_fit[mask], g_score[mask], y[mask]
    if len(y) < 20:
        raise ValueError(f"Need at least 20 rows for calibration, got {len(y)}")

    # Stratify on the scoring feature so folds reflect deployment coverage.
    strat_edges = quantile_edges(pd.Series(g_score), n_bins=n_bins)
    strat_bins = pd.cut(g_score, bins=strat_edges, include_lowest=True, labels=False)
    if np.isnan(strat_bins).any():
        raise ValueError("Unable to assign rows to stratification bins.")
    strat_bins = strat_bins.astype(int)
    bin_counts = pd.Series(strat_bins).value_counts(dropna=False)
    can_stratify = int(bin_counts.min()) >= 2 and int(bin_counts.nunique()) > 1

    # Fixed predicted-points bin edges from full segment labels (stable across repeats).
    pred_edges = quantile_edges(pd.Series(y), n_bins=n_bins)
    pred_mids = (pred_edges[:-1] + pred_edges[1:]) / 2.0
    n_pred_bins = len(pred_mids)

    curve_b_samples: list[np.ndarray] = []
    curve_c_samples: list[np.ndarray] = []
    curve_c_counts: list[np.ndarray] = []

    for r in range(n_repeats):
        split_kwargs: dict[str, Any] = {"test_size": test_size, "random_state": 60000 + r}
        if can_stratify:
            split_kwargs["stratify"] = strat_bins

        g_fit_train, _, g_score_train, g_score_test, y_train, y_test = train_test_split(
            g_fit, g_score, y, **split_kwargs
        )
        try:
            if hybrid:
                fit = fit_hybrid_games_gaussian_mle(g_fit_train, g_score_train, y_train)
            else:
                fit = fit_games_only_gaussian_mle(g_fit_train, y_train)
        except ValueError:
            continue

        mu_test = fit.predict_mean(g_score_test)
        sigma_test = fit.predict_sigma(g_score_test)

        exceed_vals = []
        for p_more in p_grid:
            z = _NORMAL.inv_cdf(1.0 - float(p_more))
            threshold = mu_test + sigma_test * z
            exceed_vals.append(float(np.mean(y_test > threshold)))
        curve_b_samples.append(np.asarray(exceed_vals, dtype=float))

        test_df = pd.DataFrame({"pred": mu_test, "actual": y_test})
        test_df["bin_id"] = pd.cut(
            test_df["pred"], bins=pred_edges, include_lowest=True, labels=False
        )
        test_df["above"] = (test_df["actual"] > test_df["pred"]).astype(float)
        grouped = (
            test_df.groupby("bin_id", dropna=False)["above"]
            .agg(["mean", "size"])
            .rename(columns={"mean": "pct", "size": "n"})
        )

        c_vals = np.full(n_pred_bins, np.nan)
        n_vals = np.zeros(n_pred_bins)
        for b in range(n_pred_bins):
            if b in grouped.index and pd.notna(grouped.loc[b, "pct"]):
                c_vals[b] = float(grouped.loc[b, "pct"])
                n_vals[b] = float(grouped.loc[b, "n"])
        curve_c_samples.append(c_vals)
        curve_c_counts.append(n_vals)

    if not curve_b_samples:
        raise ValueError("No successful calibration repeats.")

    b_arr = np.vstack(curve_b_samples)
    c_arr = np.vstack(curve_c_samples)
    n_arr = np.vstack(curve_c_counts)
    return {
        "p_more_grid": p_grid,
        "curve_b": summarize_curve(b_arr),
        "curve_c_x": pred_mids,
        "curve_c": summarize_curve(c_arr),
        "curve_c_mean_count": np.nanmean(n_arr, axis=0),
        "n_boot_used": int(len(curve_b_samples)),
        "n_obs": int(len(y)),
        "fit_games_col": fit_games_col,
        "score_games_col": score_games_col,
        "hybrid": hybrid,
    }


ATP_GS_LEVEL_LABEL = "ATP | grand_slam"


def _gender_bo3_label(val: object) -> str:
    if pd.isna(val):
        return "unknown | best_of_3"
    s = str(val).strip().lower()
    if s in {"men", "man", "male", "m"}:
        return "Men | best_of_3"
    if s in {"women", "woman", "female", "w"}:
        return "Women | best_of_3"
    return f"{s} | best_of_3"


def stratified_train_test_by_level(
    df: pd.DataFrame,
    *,
    category_col: str = "category_name",
    level_col: str = "competition_level",
    test_size: float = 0.30,
    random_state: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Within each category × competition_level stratum, sample ``test_size`` for test
    and the remainder for train, then concatenate across strata.
    """
    if not 0.0 < test_size < 1.0:
        raise ValueError(f"test_size must be in (0, 1), got {test_size}")

    work = df.copy()
    work["_level"] = [
        _level_label(c, lv)
        for c, lv in zip(work[category_col], work[level_col], strict=True)
    ]
    train_parts: list[pd.DataFrame] = []
    test_parts: list[pd.DataFrame] = []
    rng = np.random.default_rng(random_state)

    for _, grp in work.groupby("_level", sort=False):
        grp = grp.copy()
        n = len(grp)
        if n == 0:
            continue
        if n == 1:
            # Cannot hold out a stratum of size 1; keep in train only.
            train_parts.append(grp)
            continue
        n_test = int(round(n * test_size))
        n_test = min(max(n_test, 1), n - 1)
        perm = rng.permutation(n)
        test_idx = grp.index.to_numpy()[perm[:n_test]]
        train_idx = grp.index.to_numpy()[perm[n_test:]]
        test_parts.append(grp.loc[test_idx])
        train_parts.append(grp.loc[train_idx])

    if not train_parts:
        raise ValueError("Stratified split produced empty train set.")
    train_df = pd.concat(train_parts, axis=0).drop(columns=["_level"], errors="ignore")
    test_df = (
        pd.concat(test_parts, axis=0).drop(columns=["_level"], errors="ignore")
        if test_parts
        else work.iloc[0:0].drop(columns=["_level"], errors="ignore")
    )
    return train_df, test_df


def _normalize_gender(val: object) -> str | None:
    if pd.isna(val):
        return None
    s = str(val).strip().lower()
    if s in {"men", "man", "male", "m"}:
        return "men"
    if s in {"women", "woman", "female", "w"}:
        return "women"
    return None


def _fit_hybrid_segment(
    train_df: pd.DataFrame,
    *,
    score_games_col: str,
    points_col: str,
    actual_games_col: str,
) -> GamesOnlyGaussianMLE | None:
    seg = train_df.copy()
    for c in (actual_games_col, score_games_col, points_col):
        seg[c] = pd.to_numeric(seg[c], errors="coerce")
    seg = seg.dropna(subset=[actual_games_col, score_games_col, points_col])
    if len(seg) < 5:
        return None
    return fit_hybrid_games_gaussian_mle(
        mean_games=seg[actual_games_col].to_numpy(dtype=float),
        variance_games=seg[score_games_col].to_numpy(dtype=float),
        total_points=seg[points_col].to_numpy(dtype=float),
    )


def _fit_hybrid_by_best_of(
    train_df: pd.DataFrame,
    *,
    score_games_col: str = "projected_total_games",
    points_col: str = "total_points",
    best_of_col: str = "mode_best_of",
    actual_games_col: str = "total_games_played",
) -> dict[int, GamesOnlyGaussianMLE]:
    fits: dict[int, GamesOnlyGaussianMLE] = {}
    for bo in (3, 5):
        seg = train_df.loc[pd.to_numeric(train_df[best_of_col], errors="coerce") == bo]
        fit = _fit_hybrid_segment(
            seg,
            score_games_col=score_games_col,
            points_col=points_col,
            actual_games_col=actual_games_col,
        )
        if fit is not None:
            fits[bo] = fit
    return fits


def _fit_hybrid_by_gender_best_of(
    train_df: pd.DataFrame,
    *,
    gender_col: str = "competition_gender",
    score_games_col: str = "projected_total_games",
    points_col: str = "total_points",
    best_of_col: str = "mode_best_of",
    actual_games_col: str = "total_games_played",
    segments: tuple[tuple[str, int], ...] = (("men", 3), ("men", 5), ("women", 3)),
) -> dict[tuple[str, int], GamesOnlyGaussianMLE]:
    """Fit hybrid models for requested (gender, best_of) segments."""
    work = train_df.copy()
    work["_gender_norm"] = [_normalize_gender(v) for v in work[gender_col]]
    work["_bo"] = pd.to_numeric(work[best_of_col], errors="coerce")
    fits: dict[tuple[str, int], GamesOnlyGaussianMLE] = {}
    for gender, bo in segments:
        seg = work.loc[(work["_gender_norm"] == gender) & (work["_bo"] == float(bo))]
        fit = _fit_hybrid_segment(
            seg,
            score_games_col=score_games_col,
            points_col=points_col,
            actual_games_col=actual_games_col,
        )
        if fit is not None:
            fits[(gender, bo)] = fit
    return fits


def _score_above_mu(
    test_df: pd.DataFrame,
    fits_by_best_of: dict[int, GamesOnlyGaussianMLE],
    *,
    score_games_col: str = "projected_total_games",
    points_col: str = "total_points",
    best_of_col: str = "mode_best_of",
) -> pd.DataFrame:
    te = test_df.dropna(subset=[score_games_col, points_col, best_of_col]).copy()
    g = pd.to_numeric(te[score_games_col], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(te[points_col], errors="coerce").to_numpy(dtype=float)
    bo = pd.to_numeric(te[best_of_col], errors="coerce").to_numpy(dtype=float)
    mu = np.full(len(te), np.nan)
    for bo_key, fit in fits_by_best_of.items():
        mask = np.isfinite(g) & np.isfinite(y) & (bo == float(bo_key))
        if mask.any():
            mu[mask] = fit.predict_mean(g[mask])
    te["_mu"] = mu
    te["_above"] = np.where(np.isfinite(mu), (y > mu).astype(float), np.nan)
    return te.loc[np.isfinite(te["_mu"])].copy()


def _score_above_mu_by_gender_best_of(
    test_df: pd.DataFrame,
    fits_by_gender_best_of: dict[tuple[str, int], GamesOnlyGaussianMLE],
    *,
    gender_col: str = "competition_gender",
    score_games_col: str = "projected_total_games",
    points_col: str = "total_points",
    best_of_col: str = "mode_best_of",
) -> pd.DataFrame:
    te = test_df.dropna(subset=[score_games_col, points_col, best_of_col, gender_col]).copy()
    g = pd.to_numeric(te[score_games_col], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(te[points_col], errors="coerce").to_numpy(dtype=float)
    bo = pd.to_numeric(te[best_of_col], errors="coerce").to_numpy(dtype=float)
    gender = np.asarray([_normalize_gender(v) for v in te[gender_col]], dtype=object)
    mu = np.full(len(te), np.nan)
    for (g_key, bo_key), fit in fits_by_gender_best_of.items():
        mask = (
            np.isfinite(g)
            & np.isfinite(y)
            & (bo == float(bo_key))
            & (gender == g_key)
        )
        if mask.any():
            mu[mask] = fit.predict_mean(g[mask])
    te["_mu"] = mu
    te["_above"] = np.where(np.isfinite(mu), (y > mu).astype(float), np.nan)
    return te.loc[np.isfinite(te["_mu"])].copy()


def _aggregate_bootstrap_exceedance(
    samples: dict[str, list[float]],
    counts_train: dict[str, list[int]],
    counts_test: dict[str, list[int]],
    full_counts: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    # Only labels observed in at least one successful bootstrap sample.
    labels = sorted(samples.keys())
    for label in labels:
        vals = np.asarray(samples.get(label, []), dtype=float)
        vals = vals[np.isfinite(vals)]
        tr = np.asarray(counts_train.get(label, []), dtype=float)
        te = np.asarray(counts_test.get(label, []), dtype=float)
        full = full_counts.loc[full_counts["level_label"] == label]
        rows.append(
            {
                "level_label": label,
                "exceedance_mean": float(np.mean(vals)) if len(vals) else np.nan,
                "exceedance_p10": float(np.percentile(vals, 10)) if len(vals) else np.nan,
                "exceedance_p90": float(np.percentile(vals, 90)) if len(vals) else np.nan,
                "n_boot": int(len(vals)),
                "mean_n_train_matches": float(np.mean(tr)) if len(tr) else 0.0,
                "mean_n_test_matches": float(np.mean(te)) if len(te) else 0.0,
                "n_full_tournaments": int(full["n_full_tournaments"].iloc[0]) if len(full) else 0,
                "n_full_matches": int(full["n_full_matches"].iloc[0]) if len(full) else 0,
            }
        )
    return pd.DataFrame(rows)


def bootstrap_pmore_half_panels(
    match_df: pd.DataFrame,
    *,
    n_repeats: int = 200,
    test_size: float = 0.30,
    category_col: str = "category_name",
    level_col: str = "competition_level",
    gender_col: str = "competition_gender",
    season_col: str = "season_id",
    score_games_col: str = "projected_total_games",
    points_col: str = "total_points",
    best_of_col: str = "mode_best_of",
    actual_games_col: str = "total_games_played",
    random_seed: int = 70000,
) -> dict[str, Any]:
    """
    Bootstrap p-more=0.5 exceedance with stratum-wise 70/30 splits.

    Each repeat:
      - sample 30% test / 70% train within each category × competition_level
      - fit hybrid bo3 and bo5 on train
      - score test at projected games

    Returns summaries for competition-level (ex-ATP-GS), gender bo3, and ATP GS.
    """
    needed = [
        category_col,
        level_col,
        gender_col,
        season_col,
        score_games_col,
        points_col,
        best_of_col,
        actual_games_col,
    ]
    for col in needed:
        if col not in match_df.columns:
            raise KeyError(f"match_df missing required column: {col}")

    data = match_df.dropna(
        subset=[score_games_col, points_col, best_of_col, actual_games_col]
    ).copy()
    data["_level"] = [
        _level_label(c, lv)
        for c, lv in zip(data[category_col], data[level_col], strict=True)
    ]

    full_level_counts = (
        data.groupby("_level", dropna=False)
        .agg(n_full_tournaments=(season_col, "nunique"), n_full_matches=(season_col, "size"))
        .reset_index()
        .rename(columns={"_level": "level_label"})
    )
    bo3_all = data.loc[pd.to_numeric(data[best_of_col], errors="coerce") == 3].copy()
    bo3_all["_gender_level"] = [_gender_bo3_label(v) for v in bo3_all[gender_col]]
    full_gender_counts = (
        bo3_all.groupby("_gender_level", dropna=False)
        .agg(n_full_tournaments=(season_col, "nunique"), n_full_matches=(season_col, "size"))
        .reset_index()
        .rename(columns={"_gender_level": "level_label"})
    )

    level_samples: dict[str, list[float]] = {}
    level_tr: dict[str, list[int]] = {}
    level_te: dict[str, list[int]] = {}
    gender_samples: dict[str, list[float]] = {}
    gender_tr: dict[str, list[int]] = {}
    gender_te: dict[str, list[int]] = {}
    gs_samples: dict[str, list[float]] = {}
    gs_tr: dict[str, list[int]] = {}
    gs_te: dict[str, list[int]] = {}

    n_used = 0
    for r in range(n_repeats):
        try:
            tr, te = stratified_train_test_by_level(
                data,
                category_col=category_col,
                level_col=level_col,
                test_size=test_size,
                random_state=random_seed + r,
            )
            fits = _fit_hybrid_by_best_of(
                tr,
                score_games_col=score_games_col,
                points_col=points_col,
                best_of_col=best_of_col,
                actual_games_col=actual_games_col,
            )
            if not fits:
                continue
            scored = _score_above_mu(
                te,
                fits,
                score_games_col=score_games_col,
                points_col=points_col,
                best_of_col=best_of_col,
            )
        except ValueError:
            continue

        if scored.empty:
            continue
        n_used += 1

        scored["_level"] = [
            _level_label(c, lv)
            for c, lv in zip(scored[category_col], scored[level_col], strict=True)
        ]
        tr_levels = [
            _level_label(c, lv)
            for c, lv in zip(tr[category_col], tr[level_col], strict=True)
        ]
        tr_level_counts = pd.Series(tr_levels).value_counts()

        # Competition-level panel (exclude ATP GS; that has its own panel).
        for label, grp in scored.groupby("_level", dropna=False):
            label_s = str(label)
            if label_s == ATP_GS_LEVEL_LABEL:
                continue
            level_samples.setdefault(label_s, []).append(float(grp["_above"].mean()))
            level_te.setdefault(label_s, []).append(int(len(grp)))
            level_tr.setdefault(label_s, []).append(int(tr_level_counts.get(label_s, 0)))

        # Gender bo3 panel.
        if 3 in fits:
            bo3_scored = scored.loc[
                pd.to_numeric(scored[best_of_col], errors="coerce") == 3
            ].copy()
            if not bo3_scored.empty:
                bo3_scored["_gender_level"] = [
                    _gender_bo3_label(v) for v in bo3_scored[gender_col]
                ]
                tr_bo3 = tr.loc[pd.to_numeric(tr[best_of_col], errors="coerce") == 3]
                tr_g = pd.Series([_gender_bo3_label(v) for v in tr_bo3[gender_col]]).value_counts()
                for label, grp in bo3_scored.groupby("_gender_level", dropna=False):
                    label_s = str(label)
                    gender_samples.setdefault(label_s, []).append(float(grp["_above"].mean()))
                    gender_te.setdefault(label_s, []).append(int(len(grp)))
                    gender_tr.setdefault(label_s, []).append(int(tr_g.get(label_s, 0)))

        # ATP Grand Slam panel (bo5 model rows only within that level).
        gs = scored.loc[scored["_level"] == ATP_GS_LEVEL_LABEL].copy()
        if not gs.empty and 5 in fits:
            # Prefer bo5-scored rows; fall back to all GS scored rows if needed.
            gs_bo5 = gs.loc[pd.to_numeric(gs[best_of_col], errors="coerce") == 5]
            use_gs = gs_bo5 if not gs_bo5.empty else gs
            gs_samples.setdefault(ATP_GS_LEVEL_LABEL, []).append(float(use_gs["_above"].mean()))
            gs_te.setdefault(ATP_GS_LEVEL_LABEL, []).append(int(len(use_gs)))
            tr_gs = tr.loc[
                [
                    _level_label(c, lv) == ATP_GS_LEVEL_LABEL
                    for c, lv in zip(tr[category_col], tr[level_col], strict=True)
                ]
            ]
            gs_tr.setdefault(ATP_GS_LEVEL_LABEL, []).append(int(len(tr_gs)))

    if n_used == 0:
        raise ValueError("No successful bootstrap repeats for p-more 0.5 panels.")

    level_summary = _aggregate_bootstrap_exceedance(
        level_samples, level_tr, level_te, full_level_counts
    )
    gender_summary = _aggregate_bootstrap_exceedance(
        gender_samples, gender_tr, gender_te, full_gender_counts
    )
    gs_full = full_level_counts.loc[
        full_level_counts["level_label"] == ATP_GS_LEVEL_LABEL
    ].copy()
    if gs_full.empty:
        gs_full = pd.DataFrame(
            [
                {
                    "level_label": ATP_GS_LEVEL_LABEL,
                    "n_full_tournaments": 0,
                    "n_full_matches": 0,
                }
            ]
        )
    gs_summary = _aggregate_bootstrap_exceedance(gs_samples, gs_tr, gs_te, gs_full)

    # Stable plot orders.
    level_summary = level_summary.sort_values("level_label", ascending=False).reset_index(drop=True)
    gender_order = {"Men | best_of_3": 0, "Women | best_of_3": 1}
    gender_summary["_ord"] = gender_summary["level_label"].map(gender_order).fillna(99)
    # Women first in DF so Men renders above on the axis.
    gender_summary = (
        gender_summary.sort_values(["_ord", "level_label"], ascending=[False, False])
        .drop(columns=["_ord"])
        .reset_index(drop=True)
    )

    # Fixed full-dataset games-line marker (not bootstrapped).
    games_panels = _full_dataset_games_line_panels(
        data,
        category_col=category_col,
        level_col=level_col,
        gender_col=gender_col,
        best_of_col=best_of_col,
        actual_games_col=actual_games_col,
        score_games_col=score_games_col,
    )
    level_summary = _attach_games_line_exceedance(level_summary, games_panels["level"])
    gender_summary = _attach_games_line_exceedance(gender_summary, games_panels["gender"])
    gs_summary = _attach_games_line_exceedance(gs_summary, games_panels["atp_gs"])

    return {
        "level_summary": level_summary,
        "gender_summary": gender_summary,
        "atp_gs_summary": gs_summary,
        "n_boot_used": n_used,
        "n_obs": int(len(data)),
        "n_repeats": int(n_repeats),
        "test_size": float(test_size),
        "fit_mode": "best_of",
    }


def bootstrap_pmore_half_panels_by_gender(
    match_df: pd.DataFrame,
    *,
    n_repeats: int = 200,
    test_size: float = 0.30,
    category_col: str = "category_name",
    level_col: str = "competition_level",
    gender_col: str = "competition_gender",
    season_col: str = "season_id",
    score_games_col: str = "projected_total_games",
    points_col: str = "total_points",
    best_of_col: str = "mode_best_of",
    actual_games_col: str = "total_games_played",
    random_seed: int = 80000,
) -> dict[str, Any]:
    """
    Same stratified bootstrap panels as ``bootstrap_pmore_half_panels``, but fits
    separate hybrid models for (men, bo3), (men, bo5), and (women, bo3).
    """
    needed = [
        category_col,
        level_col,
        gender_col,
        season_col,
        score_games_col,
        points_col,
        best_of_col,
        actual_games_col,
    ]
    for col in needed:
        if col not in match_df.columns:
            raise KeyError(f"match_df missing required column: {col}")

    data = match_df.dropna(
        subset=[score_games_col, points_col, best_of_col, actual_games_col, gender_col]
    ).copy()
    data["_level"] = [
        _level_label(c, lv)
        for c, lv in zip(data[category_col], data[level_col], strict=True)
    ]

    full_level_counts = (
        data.groupby("_level", dropna=False)
        .agg(n_full_tournaments=(season_col, "nunique"), n_full_matches=(season_col, "size"))
        .reset_index()
        .rename(columns={"_level": "level_label"})
    )
    bo3_all = data.loc[pd.to_numeric(data[best_of_col], errors="coerce") == 3].copy()
    bo3_all["_gender_level"] = [_gender_bo3_label(v) for v in bo3_all[gender_col]]
    full_gender_counts = (
        bo3_all.groupby("_gender_level", dropna=False)
        .agg(n_full_tournaments=(season_col, "nunique"), n_full_matches=(season_col, "size"))
        .reset_index()
        .rename(columns={"_gender_level": "level_label"})
    )

    level_samples: dict[str, list[float]] = {}
    level_tr: dict[str, list[int]] = {}
    level_te: dict[str, list[int]] = {}
    gender_samples: dict[str, list[float]] = {}
    gender_tr: dict[str, list[int]] = {}
    gender_te: dict[str, list[int]] = {}
    gs_samples: dict[str, list[float]] = {}
    gs_tr: dict[str, list[int]] = {}
    gs_te: dict[str, list[int]] = {}

    n_used = 0
    fit_key_counts: dict[str, int] = {}
    for r in range(n_repeats):
        try:
            tr, te = stratified_train_test_by_level(
                data,
                category_col=category_col,
                level_col=level_col,
                test_size=test_size,
                random_state=random_seed + r,
            )
            fits = _fit_hybrid_by_gender_best_of(
                tr,
                gender_col=gender_col,
                score_games_col=score_games_col,
                points_col=points_col,
                best_of_col=best_of_col,
                actual_games_col=actual_games_col,
            )
            if not fits:
                continue
            for key in fits:
                fit_key_counts[f"{key[0]}_bo{key[1]}"] = (
                    fit_key_counts.get(f"{key[0]}_bo{key[1]}", 0) + 1
                )
            scored = _score_above_mu_by_gender_best_of(
                te,
                fits,
                gender_col=gender_col,
                score_games_col=score_games_col,
                points_col=points_col,
                best_of_col=best_of_col,
            )
        except ValueError:
            continue

        if scored.empty:
            continue
        n_used += 1

        scored["_level"] = [
            _level_label(c, lv)
            for c, lv in zip(scored[category_col], scored[level_col], strict=True)
        ]
        tr_levels = [
            _level_label(c, lv)
            for c, lv in zip(tr[category_col], tr[level_col], strict=True)
        ]
        tr_level_counts = pd.Series(tr_levels).value_counts()

        for label, grp in scored.groupby("_level", dropna=False):
            label_s = str(label)
            if label_s == ATP_GS_LEVEL_LABEL:
                continue
            level_samples.setdefault(label_s, []).append(float(grp["_above"].mean()))
            level_te.setdefault(label_s, []).append(int(len(grp)))
            level_tr.setdefault(label_s, []).append(int(tr_level_counts.get(label_s, 0)))

        # Gender panel: bo3 only, each gender scored with its own bo3 model.
        if ("men", 3) in fits or ("women", 3) in fits:
            bo3_scored = scored.loc[
                pd.to_numeric(scored[best_of_col], errors="coerce") == 3
            ].copy()
            if not bo3_scored.empty:
                bo3_scored["_gender_level"] = [
                    _gender_bo3_label(v) for v in bo3_scored[gender_col]
                ]
                tr_bo3 = tr.loc[pd.to_numeric(tr[best_of_col], errors="coerce") == 3]
                tr_g = pd.Series([_gender_bo3_label(v) for v in tr_bo3[gender_col]]).value_counts()
                for label, grp in bo3_scored.groupby("_gender_level", dropna=False):
                    label_s = str(label)
                    gender_samples.setdefault(label_s, []).append(float(grp["_above"].mean()))
                    gender_te.setdefault(label_s, []).append(int(len(grp)))
                    gender_tr.setdefault(label_s, []).append(int(tr_g.get(label_s, 0)))

        # ATP GS panel: men's bo5 model on men's bo5 GS rows.
        gs = scored.loc[scored["_level"] == ATP_GS_LEVEL_LABEL].copy()
        if not gs.empty and ("men", 5) in fits:
            gs_men_bo5 = gs.loc[
                (pd.to_numeric(gs[best_of_col], errors="coerce") == 5)
                & (np.asarray([_normalize_gender(v) for v in gs[gender_col]], dtype=object) == "men")
            ]
            if not gs_men_bo5.empty:
                gs_samples.setdefault(ATP_GS_LEVEL_LABEL, []).append(
                    float(gs_men_bo5["_above"].mean())
                )
                gs_te.setdefault(ATP_GS_LEVEL_LABEL, []).append(int(len(gs_men_bo5)))
                tr_gs = tr.loc[
                    [
                        _level_label(c, lv) == ATP_GS_LEVEL_LABEL
                        for c, lv in zip(tr[category_col], tr[level_col], strict=True)
                    ]
                ]
                gs_tr.setdefault(ATP_GS_LEVEL_LABEL, []).append(int(len(tr_gs)))

    if n_used == 0:
        raise ValueError("No successful gender-segment bootstrap repeats.")

    level_summary = _aggregate_bootstrap_exceedance(
        level_samples, level_tr, level_te, full_level_counts
    )
    gender_summary = _aggregate_bootstrap_exceedance(
        gender_samples, gender_tr, gender_te, full_gender_counts
    )
    gs_full = full_level_counts.loc[
        full_level_counts["level_label"] == ATP_GS_LEVEL_LABEL
    ].copy()
    if gs_full.empty:
        gs_full = pd.DataFrame(
            [
                {
                    "level_label": ATP_GS_LEVEL_LABEL,
                    "n_full_tournaments": 0,
                    "n_full_matches": 0,
                }
            ]
        )
    gs_summary = _aggregate_bootstrap_exceedance(gs_samples, gs_tr, gs_te, gs_full)

    level_summary = level_summary.sort_values("level_label", ascending=False).reset_index(drop=True)
    gender_order = {"Men | best_of_3": 0, "Women | best_of_3": 1}
    gender_summary["_ord"] = gender_summary["level_label"].map(gender_order).fillna(99)
    gender_summary = (
        gender_summary.sort_values(["_ord", "level_label"], ascending=[False, False])
        .drop(columns=["_ord"])
        .reset_index(drop=True)
    )

    games_panels = _full_dataset_games_line_panels(
        data,
        category_col=category_col,
        level_col=level_col,
        gender_col=gender_col,
        best_of_col=best_of_col,
        actual_games_col=actual_games_col,
        score_games_col=score_games_col,
    )
    level_summary = _attach_games_line_exceedance(level_summary, games_panels["level"])
    gender_summary = _attach_games_line_exceedance(gender_summary, games_panels["gender"])
    gs_summary = _attach_games_line_exceedance(gs_summary, games_panels["atp_gs"])

    return {
        "level_summary": level_summary,
        "gender_summary": gender_summary,
        "atp_gs_summary": gs_summary,
        "n_boot_used": n_used,
        "n_obs": int(len(data)),
        "n_repeats": int(n_repeats),
        "test_size": float(test_size),
        "fit_mode": "gender_best_of",
        "fit_key_counts": fit_key_counts,
    }


def _fit_hybrid_by_tournament_level(
    train_df: pd.DataFrame,
    *,
    category_col: str = "category_name",
    level_col: str = "competition_level",
    score_games_col: str = "projected_total_games",
    points_col: str = "total_points",
    actual_games_col: str = "total_games_played",
) -> dict[str, GamesOnlyGaussianMLE]:
    """Fit one hybrid model per category × competition_level on train."""
    work = train_df.copy()
    work["_level"] = [
        _level_label(c, lv)
        for c, lv in zip(work[category_col], work[level_col], strict=True)
    ]
    fits: dict[str, GamesOnlyGaussianMLE] = {}
    for label, grp in work.groupby("_level", sort=False):
        fit = _fit_hybrid_segment(
            grp,
            score_games_col=score_games_col,
            points_col=points_col,
            actual_games_col=actual_games_col,
        )
        if fit is not None:
            fits[str(label)] = fit
    return fits


def _score_above_mu_by_tournament_level(
    test_df: pd.DataFrame,
    fits_by_level: dict[str, GamesOnlyGaussianMLE],
    *,
    category_col: str = "category_name",
    level_col: str = "competition_level",
    score_games_col: str = "projected_total_games",
    points_col: str = "total_points",
) -> pd.DataFrame:
    te = test_df.dropna(subset=[score_games_col, points_col, category_col, level_col]).copy()
    te["_level"] = [
        _level_label(c, lv)
        for c, lv in zip(te[category_col], te[level_col], strict=True)
    ]
    g = pd.to_numeric(te[score_games_col], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(te[points_col], errors="coerce").to_numpy(dtype=float)
    labels = te["_level"].astype(str).to_numpy()
    mu = np.full(len(te), np.nan)
    for label, fit in fits_by_level.items():
        mask = np.isfinite(g) & np.isfinite(y) & (labels == label)
        if mask.any():
            mu[mask] = fit.predict_mean(g[mask])
    te["_mu"] = mu
    te["_above"] = np.where(np.isfinite(mu), (y > mu).astype(float), np.nan)
    return te.loc[np.isfinite(te["_mu"])].copy()


def bootstrap_pmore_half_panels_by_tournament_level(
    match_df: pd.DataFrame,
    *,
    n_repeats: int = 200,
    test_size: float = 0.30,
    category_col: str = "category_name",
    level_col: str = "competition_level",
    gender_col: str = "competition_gender",
    season_col: str = "season_id",
    score_games_col: str = "projected_total_games",
    points_col: str = "total_points",
    best_of_col: str = "mode_best_of",
    actual_games_col: str = "total_games_played",
    random_seed: int = 90000,
) -> dict[str, Any]:
    """
    Stratified bootstrap with one hybrid model per category × competition_level.

    Each repeat:
      - 30% test / 70% train within each tournament level
      - fit a separate hybrid model on each level's train matches
      - score that level's test matches with its own model
    """
    needed = [
        category_col,
        level_col,
        gender_col,
        season_col,
        score_games_col,
        points_col,
        best_of_col,
        actual_games_col,
    ]
    for col in needed:
        if col not in match_df.columns:
            raise KeyError(f"match_df missing required column: {col}")

    data = match_df.dropna(
        subset=[score_games_col, points_col, best_of_col, actual_games_col]
    ).copy()
    data["_level"] = [
        _level_label(c, lv)
        for c, lv in zip(data[category_col], data[level_col], strict=True)
    ]

    full_level_counts = (
        data.groupby("_level", dropna=False)
        .agg(n_full_tournaments=(season_col, "nunique"), n_full_matches=(season_col, "size"))
        .reset_index()
        .rename(columns={"_level": "level_label"})
    )
    bo3_all = data.loc[pd.to_numeric(data[best_of_col], errors="coerce") == 3].copy()
    bo3_all["_gender_level"] = [_gender_bo3_label(v) for v in bo3_all[gender_col]]
    full_gender_counts = (
        bo3_all.groupby("_gender_level", dropna=False)
        .agg(n_full_tournaments=(season_col, "nunique"), n_full_matches=(season_col, "size"))
        .reset_index()
        .rename(columns={"_gender_level": "level_label"})
    )

    level_samples: dict[str, list[float]] = {}
    level_tr: dict[str, list[int]] = {}
    level_te: dict[str, list[int]] = {}
    gender_samples: dict[str, list[float]] = {}
    gender_tr: dict[str, list[int]] = {}
    gender_te: dict[str, list[int]] = {}
    gs_samples: dict[str, list[float]] = {}
    gs_tr: dict[str, list[int]] = {}
    gs_te: dict[str, list[int]] = {}

    n_used = 0
    fit_key_counts: dict[str, int] = {}
    for r in range(n_repeats):
        try:
            tr, te = stratified_train_test_by_level(
                data,
                category_col=category_col,
                level_col=level_col,
                test_size=test_size,
                random_state=random_seed + r,
            )
            fits = _fit_hybrid_by_tournament_level(
                tr,
                category_col=category_col,
                level_col=level_col,
                score_games_col=score_games_col,
                points_col=points_col,
                actual_games_col=actual_games_col,
            )
            if not fits:
                continue
            for key in fits:
                fit_key_counts[key] = fit_key_counts.get(key, 0) + 1
            scored = _score_above_mu_by_tournament_level(
                te,
                fits,
                category_col=category_col,
                level_col=level_col,
                score_games_col=score_games_col,
                points_col=points_col,
            )
        except ValueError:
            continue

        if scored.empty:
            continue
        n_used += 1

        tr_levels = [
            _level_label(c, lv)
            for c, lv in zip(tr[category_col], tr[level_col], strict=True)
        ]
        tr_level_counts = pd.Series(tr_levels).value_counts()

        for label, grp in scored.groupby("_level", dropna=False):
            label_s = str(label)
            if label_s == ATP_GS_LEVEL_LABEL:
                continue
            level_samples.setdefault(label_s, []).append(float(grp["_above"].mean()))
            level_te.setdefault(label_s, []).append(int(len(grp)))
            level_tr.setdefault(label_s, []).append(int(tr_level_counts.get(label_s, 0)))

        # Men vs women aggregates: score already level-specific; pool bo3.
        bo3_scored = scored.loc[
            pd.to_numeric(scored[best_of_col], errors="coerce") == 3
        ].copy()
        if not bo3_scored.empty:
            bo3_scored["_gender_level"] = [
                _gender_bo3_label(v) for v in bo3_scored[gender_col]
            ]
            tr_bo3 = tr.loc[pd.to_numeric(tr[best_of_col], errors="coerce") == 3]
            tr_g = pd.Series([_gender_bo3_label(v) for v in tr_bo3[gender_col]]).value_counts()
            for label, grp in bo3_scored.groupby("_gender_level", dropna=False):
                label_s = str(label)
                gender_samples.setdefault(label_s, []).append(float(grp["_above"].mean()))
                gender_te.setdefault(label_s, []).append(int(len(grp)))
                gender_tr.setdefault(label_s, []).append(int(tr_g.get(label_s, 0)))

        gs = scored.loc[scored["_level"] == ATP_GS_LEVEL_LABEL].copy()
        if not gs.empty and ATP_GS_LEVEL_LABEL in fits:
            gs_samples.setdefault(ATP_GS_LEVEL_LABEL, []).append(float(gs["_above"].mean()))
            gs_te.setdefault(ATP_GS_LEVEL_LABEL, []).append(int(len(gs)))
            gs_tr.setdefault(ATP_GS_LEVEL_LABEL, []).append(
                int(tr_level_counts.get(ATP_GS_LEVEL_LABEL, 0))
            )

    if n_used == 0:
        raise ValueError("No successful per-tournament-level bootstrap repeats.")

    level_summary = _aggregate_bootstrap_exceedance(
        level_samples, level_tr, level_te, full_level_counts
    )
    gender_summary = _aggregate_bootstrap_exceedance(
        gender_samples, gender_tr, gender_te, full_gender_counts
    )
    gs_full = full_level_counts.loc[
        full_level_counts["level_label"] == ATP_GS_LEVEL_LABEL
    ].copy()
    if gs_full.empty:
        gs_full = pd.DataFrame(
            [
                {
                    "level_label": ATP_GS_LEVEL_LABEL,
                    "n_full_tournaments": 0,
                    "n_full_matches": 0,
                }
            ]
        )
    gs_summary = _aggregate_bootstrap_exceedance(gs_samples, gs_tr, gs_te, gs_full)

    level_summary = level_summary.sort_values("level_label", ascending=False).reset_index(
        drop=True
    )
    gender_order = {"Men | best_of_3": 0, "Women | best_of_3": 1}
    gender_summary["_ord"] = gender_summary["level_label"].map(gender_order).fillna(99)
    gender_summary = (
        gender_summary.sort_values(["_ord", "level_label"], ascending=[False, False])
        .drop(columns=["_ord"])
        .reset_index(drop=True)
    )

    games_panels = _full_dataset_games_line_panels(
        data,
        category_col=category_col,
        level_col=level_col,
        gender_col=gender_col,
        best_of_col=best_of_col,
        actual_games_col=actual_games_col,
        score_games_col=score_games_col,
    )
    level_summary = _attach_games_line_exceedance(level_summary, games_panels["level"])
    gender_summary = _attach_games_line_exceedance(gender_summary, games_panels["gender"])
    gs_summary = _attach_games_line_exceedance(gs_summary, games_panels["atp_gs"])

    return {
        "level_summary": level_summary,
        "gender_summary": gender_summary,
        "atp_gs_summary": gs_summary,
        "n_boot_used": n_used,
        "n_obs": int(len(data)),
        "n_repeats": int(n_repeats),
        "test_size": float(test_size),
        "fit_mode": "tournament_level",
        "fit_key_counts": fit_key_counts,
    }
