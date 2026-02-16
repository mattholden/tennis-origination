"""
Season competitors: API endpoint and fetch (parameterized by season_id).

Endpoint: tennis/{access_level}/v3/{language_code}/seasons/{season_id}/competitors.json
Returns list of players active for that season/tournament.
"""

ENDPOINT_PATH = "seasons/{season_id}/competitors.json"


def fetch_season_competitors(client, *, season_id: str) -> dict:
    """
    Fetch competitors for a single season from the Sportradar API.
    Pass the season id (e.g. from the seasons table) as path parameter.
    """
    return client.get(ENDPOINT_PATH, season_id=season_id)
