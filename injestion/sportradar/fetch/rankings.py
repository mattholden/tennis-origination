"""
Ranking: API endpoint and fetch (parameterized by sport_event_id).

Endpoint: tennis/{access_level}/v3/{language_code}/rankings/{competition_id}.json
Returns rankings for a given competition.
"""

ENDPOINT_PATH = "rankings.json"


async def fetch_rankings(client) -> dict:
    """
    Fetch rankings for a given competition from the Sportradar API.
    """
    return await client.get_async(ENDPOINT_PATH)