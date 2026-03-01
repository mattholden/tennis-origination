"""
OpticOdds fixtures endpoint: API endpoint and fetch.

Endpoint: GET /fixtures with query params (sport, league, page).
Bulk import: no year or season_week; iterate all pages using total_pages from response.
"""


async def fetch_fixtures_page(
    client,
    *,
    league: str,
    page: int = 1,
    sport: str = "tennis",
) -> dict:
    """
    Fetch odds for a given fixture from the OddsJam API.
    """
    params = {
        "sport": sport,
        "league": league.lower(),
        "page": page,
        "start_date_after": "2023-12-29", # Earliest data is 2023-12-30
    }
    return await client.get_async("fixtures", params=params)