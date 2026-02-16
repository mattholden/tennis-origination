"""
Season competitors pipeline: pull season_ids from BQ -> fetch -> filter -> transform -> upload.
Closed loop: run in isolation via Runner.run("season_competitors"). Depends on seasons table being populated.
"""

import core.raw_store


def run(client, manager, bq) -> None:
    """End-to-end: get season ids from BQ, fetch competitors, filter by those ids, write to BigQuery."""
    season_ids = bq.get_season_ids_for_major_competitions(
        manager.get_table_id("seasons")
    )
    table_id = manager.get_table_id("season_competitors")

    #all_raw_by_season = {}
    for season_id in season_ids:
        raw = manager.get_raw("season_competitors", client, season_id=season_id)
        #all_raw_by_season[season_id] = raw
        rows = manager.raw_to_rows("season_competitors", raw, season_id=season_id)
        bq.write_rows(table_id, rows)

    #core.raw_store.save_raw_to_json(
    #    {"by_season": all_raw_by_season},
    #    "season_competitors",
    #    source="sportradar",
    #)