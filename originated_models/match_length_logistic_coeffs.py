"""Stored logistic coefficients for ATP match-length probabilities.

These coefficients are fit on favorites-only implied probabilities (p > 0.5),
deduped to one row per fixture, matching the modeling setup in
`originated_models/match_length.ipynb`.
"""

from __future__ import annotations

import math

MATCH_LENGTH_LOGISTIC_COEFFS: dict[str, dict[str, dict[str, float]]] = {
    "best_of_3": {
        "2_sets": {
            "intercept": -0.7928334602044133,
            "coef": 1.9432380976842325,
        },
        "3_sets": {
            "intercept": 0.7860561006249647,
            "coef": -1.9347307934521145,
        },
    },
    "best_of_5": {
        "3_sets": {
            "intercept": -1.7362278879455222,
            "coef": 1.9476380418329697,
        },
        "4_sets": {
            "intercept": -0.2649731779420392,
            "coef": -0.4892659063618217,
        },
        "5_sets": {
            "intercept": 0.20724184588699668,
            "coef": -1.9891344209309787,
        },
    },
}


def american_to_implied_prob(moneyline: float) -> float:
    """Convert American odds to implied probability for the quoted side."""
    if moneyline == 0:
        raise ValueError("Moneyline cannot be 0.")
    if moneyline > 0:
        return 100.0 / (moneyline + 100.0)
    return (-moneyline) / ((-moneyline) + 100.0)


def moneyline_to_favorite_prob(moneyline: float) -> float:
    """Convert a side's moneyline to favorite-side win probability."""
    side_prob = american_to_implied_prob(moneyline)
    return max(side_prob, 1.0 - side_prob)


def _sigmoid(z: float) -> float:
    # Stable sigmoid implementation.
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def get_match_length_probabilities_from_favorite_prob(
    favorite_prob: float,
    best_of: int,
    coeffs: dict[str, dict[str, dict[str, float]]] | None = None,
) -> dict[str, float]:
    """Return normalized set-count probabilities from stored logistic curves.

    Returns keys like {'2_sets': p, '3_sets': p} for best_of=3 and
    {'3_sets': p, '4_sets': p, '5_sets': p} for best_of=5.
    """
    if not (0.0 <= favorite_prob <= 1.0):
        raise ValueError(f"favorite_prob must be in [0, 1], got {favorite_prob}")

    coeff_table = coeffs or MATCH_LENGTH_LOGISTIC_COEFFS
    best_of_key = "best_of_3" if int(best_of) == 3 else "best_of_5" if int(best_of) == 5 else None
    if best_of_key is None:
        raise ValueError(f"best_of must be 3 or 5, got {best_of}")

    raw_probs: dict[str, float] = {}
    for set_key, params in coeff_table[best_of_key].items():
        z = params["intercept"] + params["coef"] * favorite_prob
        raw_probs[set_key] = _sigmoid(z)

    denom = sum(raw_probs.values())
    if denom <= 0:
        n = len(raw_probs)
        return {k: 1.0 / n for k in raw_probs}
    return {k: v / denom for k, v in raw_probs.items()}


def get_match_length_probabilities_from_moneyline(
    moneyline: float,
    best_of: int,
    coeffs: dict[str, dict[str, dict[str, float]]] | None = None,
) -> dict[str, float]:
    """Convenience wrapper: moneyline -> favorite prob -> normalized set probs."""
    favorite_prob = moneyline_to_favorite_prob(moneyline)
    return get_match_length_probabilities_from_favorite_prob(
        favorite_prob=favorite_prob,
        best_of=best_of,
        coeffs=coeffs,
    )
