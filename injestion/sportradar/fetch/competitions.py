"""
Competitions resource: API endpoint and fetch.
"""

ENDPOINT_PATH = "competitions.json"


async def fetch_competitions(client) -> dict:
    """
    Fetch competitions from the Sportradar API.
    Returns full response: {"generated_at": "...", "competitions": [...]}.
    """
    return await client.get_async(ENDPOINT_PATH)
