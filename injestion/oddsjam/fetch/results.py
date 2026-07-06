"""
OpticOdds results endpoint: API endpoint and fetch (parameterized by fixture_id).

Endpoint: GET /fixtures/results
Query params: fixture_id
Returns raw response: {"data": [{...}]}
"""


async def fetch_results(
    client,
    *,
    fixture_id: str,
) -> dict:
    """
    Fetch results for one fixture from the OpticOdds API.
    """
    params = {"fixture_id": fixture_id}
    return await client.get_async("fixtures/results", params=params)
