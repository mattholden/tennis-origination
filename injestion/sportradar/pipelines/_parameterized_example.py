"""
Example pattern for a parameterized pipeline: pull param list from BigQuery, then fetch/transform/upload.

Do not import this in registry until the resource (e.g. season_summaries) exists.
Uncomment and adapt when adding a resource that needs e.g. season_id from the seasons table.
"""


def run(client, manager, bq) -> None:
    """Example: season_summaries needs season_id for each request."""
    # 1. Pull parameters from BigQuery (table populated by the "seasons" pipeline)
    seasons_table_id = manager.get_table_id("seasons")
    season_ids = bq.get_param_list(seasons_table_id, "id")

    # 2. Fetch + transform for each param; accumulate rows
    all_rows = []
    for season_id in season_ids:
        rows = manager.load_resource("season_summaries", client, season_id=season_id)
        all_rows.extend(rows)

    # 3. Upload to this resource's table
    table_id = manager.get_table_id("season_summaries")
    bq.write_rows(table_id, all_rows)

    # Alternative: write per season to limit memory
    # for season_id in season_ids:
    #     rows = manager.load_resource("season_summaries", client, season_id=season_id)
    #     bq.write_rows(manager.get_table_id("season_summaries"), rows)
