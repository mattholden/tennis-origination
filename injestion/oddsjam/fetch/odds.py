"""
OddsJam odds endpoint: API endpoint and fetch (parameterized by fixture_id).

Endpoint: https://api.oddsjam.com/v1/odds/{fixture_id}
Returns odds for a given fixture.
"""

ENDPOINT_PATH = "odds.json"


async def fetch_odds(client, fixture_id: str) -> dict:
    """
    Fetch odds for a given fixture from the OddsJam API.
    """
    return await client.get_async(ENDPOINT_PATH, fixture_id=fixture_id)