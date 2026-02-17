"""
Competitors pipeline: pull competitor_ids from BQ -> fetch (async, parallel) -> transform -> upload.

One API call (competitor profile) feeds two tables: competitors and surface_stats.
Closed loop: Runner.run("competitors"). Depends on season_competitors table being populated.

Subsample: set SUBSAMPLE_COMPETITORS=10 in env to process only the first 10 (for debugging).
"""

import asyncio
import os

max_concurrent_requests = 8
semaphore = asyncio.Semaphore(max_concurrent_requests)


async def run(client, manager, bq) -> None:
    """End-to-end: get competitor ids from BQ, fetch profiles in parallel, split into two tables, write."""
    competitor_ids = bq.get_competitor_ids_from_season_competitors_table(
        manager.get_table_id("season_competitors")
    )
    # subsample = os.environ.get("SUBSAMPLE_COMPETITORS")
    # if subsample is not None:
    #     n = int(subsample)
    #     competitor_ids = competitor_ids[:n]
    #     print(f"Subsample: using first {n} competitors (SUBSAMPLE_COMPETITORS={subsample})")
    profile_table_id = manager.get_table_id("competitors")
    surface_stats_table_id = manager.get_table_id("surface_stats")

    async def fetch_competitor_profile(competitor_id: str) -> dict:
        async with semaphore:
            return await manager.get_raw_async("competitors", client, competitor_id=competitor_id)

    total = len(competitor_ids)
    pending = {asyncio.create_task(fetch_competitor_profile(cid)) for cid in competitor_ids}
    player_profiles = []
    surface_stats = []
    completed = 0

    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            try:
                raw = task.result()
            except Exception as e:
                print(f"Error fetching competitor profile: {e}")
                continue
            player_profiles.extend(manager.raw_to_rows("competitors", raw))
            surface_stats.extend(manager.raw_to_rows("surface_stats", raw))
            completed += 1
        msg = f"Fetched {completed}/{total} competitor profiles"
        print(f"\r{msg:<50}", end="", flush=True)

    print()
    bq.write_rows(profile_table_id, player_profiles)
    bq.write_rows(surface_stats_table_id, surface_stats)

            

    