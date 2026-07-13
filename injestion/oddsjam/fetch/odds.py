"""
OpticOdds odds endpoint: API endpoint and fetch (parameterized by fixture_id).

Endpoint: GET /fixtures/odds or /fixtures/odds/historical
Query params: fixture_id, sportsbook (list, max 5), market (list), is_main.
Returns merged raw response: {"data": [{ "odds": [...] }]}.
"""

from typing import Any, Optional

# Default request params. API allows max 5 sportsbooks per request; this module
# automatically chunks larger sportsbook lists and merges chunk responses.
MAX_SPORTSBOOKS_PER_REQUEST = 5

DEFAULT_SPORTSBOOKS = [
    "betrivers", 
    "bovada", 
    "hard_rock", 
    "pinnacle", 
    "fanduel",
    "draftkings",
    "bet365",
    "caesars",
    "betmgm",
    "circa_sports",
    "circa_vegas",
    "espn_bet",
    "betrivers",
    "underdog_sportsbook",
    "betano",
]

DEFAULT_MARKETS = [
    "1st_set_game_1_moneyline",
    "1st_set_game_1_total_points",
    "1st_set_game_2_moneyline",
    "1st_set_game_2_total_points",
    "1st_set_game_3_moneyline",
    "1st_set_game_3_total_points",
    "1st_set_game_4_moneyline",
    "1st_set_game_4_total_points",
    "1st_set_game_5_moneyline",
    "1st_set_game_5_total_points",
    "1st_set_game_6_moneyline",
    "1st_set_game_6_total_points",
    "moneyline",
    "total_games",
    "total_break_points", 
    "total_tie_breaks", 
    "total_aces",
    "total_sets",
    "total_breaks",
    "player_sets_won",
    "player_first_serve_percentage",
    "player_aces",
    "player_games_won",
    "player_double_faults",
    "player_break_points_won", 
    "player_aces_+_double_faults",
    "player_service_games_lost",
    '1st_set_total_games',
    '1st_set_player_aces',
    '1st_set_total_aces',
    '1st_set_total_breaks',
    "1st_set_total_points",
    "1st_set_player_games_won",
]


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _chunk(values: list[str], chunk_size: int) -> list[list[str]]:
    return [values[i : i + chunk_size] for i in range(0, len(values), chunk_size)]


def _merge_odds_payloads(payloads: list[dict[str, Any]], requested_fixture_id: str) -> dict[str, Any]:
    """
    Merge odds payloads fetched per sportsbook chunk into one payload.

    Any chunk missing "data" raises ValueError so the caller can trigger
    fixture-level retry logic.
    """
    if not payloads:
        return {"data": []}

    fixture_rows: list[dict[str, Any]] = []
    for payload in payloads:
        if "data" not in payload:
            raise ValueError("Odds API response missing 'data' key in sportsbook chunk; cannot process.")
        fixture_rows.extend(payload.get("data") or [])

    # Keep top-level fields from first payload, but replace data with merged data.
    merged_payload = dict(payloads[0])
    if not fixture_rows:
        merged_payload["data"] = []
        return merged_payload

    merged_by_fixture_id: dict[str, dict[str, Any]] = {}
    for fixture in fixture_rows:
        fixture_id = fixture.get("id") or requested_fixture_id
        key = str(fixture_id) if fixture_id is not None else f"unknown_{len(merged_by_fixture_id)}"

        if key not in merged_by_fixture_id:
            base = dict(fixture)
            base["id"] = fixture_id
            base["odds"] = list(fixture.get("odds") or [])
            merged_by_fixture_id[key] = base
            continue

        # Merge odds arrays; keep first fixture metadata seen for consistency.
        existing = merged_by_fixture_id[key]
        existing_odds = list(existing.get("odds") or [])
        existing_odds.extend(fixture.get("odds") or [])
        existing["odds"] = existing_odds

    # Dedupe merged odds lines by odds id within each fixture.
    for fixture in merged_by_fixture_id.values():
        deduped_odds: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for odds_line in fixture.get("odds") or []:
            odds_id = odds_line.get("id")
            if odds_id is None:
                deduped_odds.append(odds_line)
                continue
            odds_id_str = str(odds_id)
            if odds_id_str in seen_ids:
                continue
            seen_ids.add(odds_id_str)
            deduped_odds.append(odds_line)
        fixture["odds"] = deduped_odds

    merged_payload["data"] = list(merged_by_fixture_id.values())
    return merged_payload


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
    If sportsbooks > 5, issue multiple requests in sportsbook chunks and merge.
    """
    sportsbooks = sportsbooks or DEFAULT_SPORTSBOOKS
    sportsbooks = _dedupe_preserve_order(sportsbooks)
    if not sportsbooks:
        raise ValueError("At least one sportsbook is required to fetch odds.")
    markets = markets or DEFAULT_MARKETS
    path = "fixtures/odds/historical" if historical else "fixtures/odds"
    payloads: list[dict[str, Any]] = []
    for sportsbook_chunk in _chunk(sportsbooks, MAX_SPORTSBOOKS_PER_REQUEST):
        params = {
            "fixture_id": fixture_id,
            "sportsbook": sportsbook_chunk,
            "market": markets,
            "is_main": is_main,
        }
        payloads.append(await client.get_async(path, params=params))
    return _merge_odds_payloads(payloads, fixture_id)
