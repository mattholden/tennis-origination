"""
Competitions pipeline: fetch -> (save raw for review) -> transform -> upload.
No parameters from BQ. Closed loop: run in isolation via Runner.run("competitions").
"""

import core.raw_store


async def run(client, manager, bq) -> None:
    """End-to-end: fetch, optionally save raw JSON, transform, write to BigQuery."""
    raw = await manager.get_raw_async("competitions", client)
    # Save raw for review when defining schema (keep or comment out once table is live)
    #core.raw_store.save_raw_to_json(raw, "competitions", source="sportradar")

    rows = manager.raw_to_rows("competitions", raw)
    table_id = manager.get_table_id("competitions")
    bq.write_rows(table_id, rows)
