"""
Event summary: API endpoint and fetch (parameterized by sport_event_id).

Endpoint: tennis/{access_level}/v3/{language_code}/sport_events/{sport_event_id}/summary.json
Returns summary of a single match.
"""

ENDPOINT_PATH = "sport_events/{sport_event_id}/timeline.json"


async def fetch_event_summary(client, *, sport_event_id: str) -> dict:
    """
    Fetch summary for a single match from the Sportradar API.
    Pass the sport_event_id (e.g. from the season_brackets table) as path parameter.
    """
    return await client.get_async(ENDPOINT_PATH, sport_event_id=sport_event_id)