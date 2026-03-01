"""
Rankings pipeline: fetch -> transform -> upload.
No parameters from BQ. Closed loop: run in isolation via Runner.run("rankings").
"""

import injestion.core.raw_store


async def run(client, manager, bq) -> None:
    """End-to-end: fetch, transform, write to BigQuery."""
    table_id = manager.get_table_id("rankings")
    raw = await manager.get_raw_async("rankings", client)
    rows = manager.raw_to_rows("rankings", raw)
    bq.write_rows(table_id, rows)

    #core.raw_store.save_raw_to_json(raw, "rankings", source="sportradar")