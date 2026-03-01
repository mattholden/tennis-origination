"""
OpticOdds odds endpoint: API endpoint and fetch (parameterized by fixture_id).

Endpoint: GET /fixtures/odds or /fixtures/odds/historical
Query params: fixture_id, sportsbook (list, max 5), market (list), is_main.
Returns raw response: {"data": [{ "odds": [...] }]}.
"""

from typing import Optional

# Default request params (API allows max 5 sportsbooks per request). Match main.py for consistency.
DEFAULT_SPORTSBOOKS = ["betrivers", "bovada", "hard_rock", "pinnacle", "draftkings"]
DEFAULT_MARKETS = [
    "moneyline",
    "total_games",
    "total_break_points", 
    "player_break_points_won", 
    "total_tie_breaks", 
    "total_double_faults",
    "total_aces",
    "total_sets",
    "player_sets_won",
    "player_first_serve_percentage",
    "total_breaks",
    "player_aces",
    "player_games_won",
    "player_aces_+_double_faults",
    "player_double_faults",
    "total_double_faults",
    '1st_set_total_games',
    '1st_set_player_aces',
    '1st_set_player_games_won',
    '1st_set_total_aces',
    '1st_set_total_breaks'
]


async def fetch_odds(
    client,
    *,
    fixture_id: str,
    sportsbooks: Optional[list[str]] = None,
    markets: Optional[list[str]] = None,
    is_main: bool = True,
    historical: bool = True,
) -> dict:
    """
    Fetch odds for one fixture from the OpticOdds API.
    historical=True uses /fixtures/odds/historical (for completed fixtures).
    """
    sportsbooks = sportsbooks or DEFAULT_SPORTSBOOKS[:5]
    markets = markets or DEFAULT_MARKETS
    params = {
        "fixture_id": fixture_id,
        "sportsbook": sportsbooks,
        "market": markets,
        "is_main": is_main,
    }
    path = "fixtures/odds/historical" if historical else "fixtures/odds"
    return await client.get_async(path, params=params)
