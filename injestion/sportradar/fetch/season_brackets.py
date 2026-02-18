"""
Season brackets: API endpoint and fetch (parameterized by season_id).

Endpoint: tennis/{access_level}/v3/{language_code}/seasons/{season_id}/stages_groups_cup_rounds.json
Returns list of stages, groups, and cup rounds for that season/tournament.
"""

ENDPOINT_PATH = "seasons/{season_id}/stages_groups_cup_rounds.json"


async def fetch_season_brackets(client, *, season_id: str) -> dict:
    """
    Fetch brackets for a single season from the Sportradar API.
    Pass the season id (e.g. from the seasons table) as path parameter.
    """
    return await client.get_async(ENDPOINT_PATH, season_id=season_id)