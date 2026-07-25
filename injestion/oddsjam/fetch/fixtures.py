"""
OpticOdds fixtures endpoint: API endpoint and fetch.

Endpoint: GET /fixtures with query params (sport, league, page).
Bulk import: no year or season_week; iterate pages until has_more is false.
"""

# Earliest observed tennis data is 2023-12-30; use prior day as inclusive lower bound.
DEFAULT_START_DATE_AFTER = "2023-12-29"


async def fetch_fixtures_page(
    client,
    *,
    league: str,
    page: int = 1,
    sport: str = "tennis",
    start_date_after: str = DEFAULT_START_DATE_AFTER,
) -> dict:
    """
    Fetch odds for a given fixture from the OddsJam API.
    """
    params = {
        "sport": sport,
        "league": league.lower(),
        "page": page,
        "start_date_after": start_date_after,
    }
    return await client.get_async("fixtures", params=params)