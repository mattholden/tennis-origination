"""
Seasons pipeline: pull allowed competition_ids from BQ -> fetch -> filter -> transform -> upload.
Closed loop: run in isolation via Runner.run("seasons"). Depends on competitions table being populated.
"""

import core.raw_store


async def run(client, manager, bq) -> None:
    """End-to-end: get competition ids from BQ, fetch seasons, filter by those ids, write to BigQuery."""
    allowed_competition_ids = bq.get_competition_ids_from_competitions_table(
        manager.get_table_id("competitions")
    )

    raw = await manager.get_raw_async("seasons", client)
    #core.raw_store.save_raw_to_json(raw, "seasons", source="sportradar")

    rows = manager.raw_to_rows("seasons", raw, allowed_competition_ids=allowed_competition_ids)
    table_id = manager.get_table_id("seasons")
    bq.write_rows(table_id, rows)