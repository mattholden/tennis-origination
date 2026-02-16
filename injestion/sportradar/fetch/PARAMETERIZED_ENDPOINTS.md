# Parameterized Sportradar endpoints

Endpoints that require path parameters use the same pattern: define a path template with `{param_name}` placeholders and pass values via `client.get(path, **path_params)`.

## Client usage

```python
# No parameters (existing)
client.get("seasons.json")

# With path parameters
client.get("seasons/{season_id}/competitors.json", season_id="sr:season:12345")
```

The client substitutes each keyword argument into the path; names must match the placeholders.

## Fetch module pattern

For each parameterized endpoint, add a module under `fetch/` with:

1. **ENDPOINT_PATH** – path template with `{param_name}` placeholders.
2. **fetch_*(client, *, param1, param2, ...)** – function that calls `client.get(ENDPOINT_PATH, param1=param1, param2=param2, ...)`.

Example: `fetch/season_competitors.py` (implemented).

## Endpoint reference (path templates)

| Resource            | Path template                                              | Parameters        |
|---------------------|------------------------------------------------------------|-------------------|
| Season competitors  | `seasons/{season_id}/competitors.json`                     | `season_id`       |
| Player profile      | `competitors/{competitor_id}/profile.json`                 | `competitor_id`   |
| Season bracket      | `seasons/{season_id}/stages_groups_cup_rounds.json`        | `season_id`       |
| Match summary       | `sport_events/{sport_event_id}/summary.json`               | `sport_event_id`  |
| Match timeline      | `sport_events/{sport_event_id}/timeline.json`              | `sport_event_id`  |

To add a new one: create a fetch module (e.g. `competitor_profile.py`), register the resource in the manager with that fetch, and in the pipeline pull the param list from BQ (e.g. `get_param_list(..., "id")`) and loop `manager.get_raw(name, client, param=value)`.
