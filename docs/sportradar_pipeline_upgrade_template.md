# Sportradar Pipeline Upgrade Template

This guide documents the upgrade pattern implemented for the `season_competitors` pipeline and serves as a template for upgrading the rest of Sportradar ingestion pipelines.

The goal is to make pipelines:
- idempotent on reruns
- retry-aware for transient API failures
- resumable via failed-only reruns
- explicit about processing scope

---

## Reference Implementation: `season_competitors`

### 1) Scope selection

**What changed**
- Replaced major-competition-only season selection with a date-window selector from `sr_seasons`.

**Current selector**
- `start_date >= SR_SEASON_MIN_START_DATE` (default: `2026-01-01`)
- `start_date <= CURRENT_DATE()`

**Code locations**
- `injestion/core/bq.py`
  - `get_season_ids_from_seasons_table_by_min_start_date(...)`
- `injestion/sportradar/pipelines/season_competitors.py`
  - uses helper above unless JSON override is supplied

---

### 2) Insert-only merge dedupe

**What changed**
- Replaced append-only `write_rows(...)` with merge-on-natural-key.

**Natural key**
- `(season_id, competitor_id)`

**Behavior**
- Insert unseen key pairs only (`WHEN NOT MATCHED THEN INSERT`)
- Drop rows missing required key columns

**Code locations**
- `injestion/core/bq.py`
  - `merge_season_competitor_rows_by_season_and_competitor(...)`
- `injestion/sportradar/pipelines/season_competitors.py`
  - calls merge helper for each fetched season payload

---

### 3) Retry at entity-id level

**What changed**
- Added retry loop per `season_id`.

**Current settings**
- `SEASON_COMPETITORS_MAX_RETRIES = 3`
- increasing delay by attempt (`SEASON_COMPETITORS_RETRY_DELAY_SECONDS * attempt`)

**Behavior**
- Log each failed attempt
- Retry transient fetch errors
- Raise after max retries for that `season_id`

**Code location**
- `injestion/sportradar/pipelines/season_competitors.py`

---

### 4) Failed-id checkpoint + failed-only rerun

**What changed**
- Added failed-id checkpoint file and optional override input.

**Failed checkpoint path**
- `raw_data/sportradar/failed_processes/season_competitors_failed_season_ids.json`

**Run behavior**
- File is reset to an empty list at run start
- Failed IDs are checkpointed during run (atomic temp-file replace)
- End-of-run file contains only failures from that run

**Failed-only override**
- Env var: `SR_SEASON_COMPETITORS_IDS_JSON`
- If set, pipeline reads IDs from that JSON list instead of normal season query

**Makefile flags**
- `SR_SEASON_COMPETITORS_FAILED_ONLY ?= 0`
- `SR_SEASON_COMPETITORS_FAILED_IDS_JSON ?= raw_data/sportradar/failed_processes/season_competitors_failed_season_ids.json`

**Commands**
- normal:
  - `make sr-pipeline-season_competitors`
- failed-only:
  - `make sr-pipeline-season_competitors SR_SEASON_COMPETITORS_FAILED_ONLY=1`
- failed-only with custom file:
  - `make sr-pipeline-season_competitors SR_SEASON_COMPETITORS_FAILED_ONLY=1 SR_SEASON_COMPETITORS_FAILED_IDS_JSON=<path>`

---

## Upgrade Checklist for Other Sportradar Pipelines

Apply this sequence pipeline-by-pipeline.

1. **Define the processing entity key**
   - Examples: `season_id`, `sport_event_id`, `competitor_id`.

2. **Define processing scope selector**
   - Pull candidate IDs from upstream table(s) with explicit date/window constraints.
   - Add optional env-driven overrides where useful.

3. **Define natural dedupe key for target table(s)**
   - Add merge helper in `injestion/core/bq.py` if one does not exist.
   - Use insert-only merge unless update semantics are explicitly needed.

4. **Add retries at entity-id fetch boundary**
   - Retry count defaults to 3 unless endpoint-specific behavior requires different tuning.
   - Log failures with concise status/error context.

5. **Add failed-id checkpoint file**
   - Use `raw_data/sportradar/failed_processes/<pipeline>_failed_<entity>_ids.json`.
   - Persist atomically during run.

6. **Add failed-only rerun input**
   - Add `<PIPELINE>_IDS_JSON` env override in the pipeline.
   - Add Makefile toggle and optional custom file path variable.

7. **Validate**
   - Syntax check changed files.
   - Run normal mode and failed-only mode smoke tests.
   - Confirm rerun idempotency by checking key-level duplicate counts do not grow.

---

## Notes on Modularity

- Keep table-specific wrappers where behavior is intentionally different.
- Share only low-level merge staging primitives where behavior is truly common.
- Do not over-generalize dedupe semantics across resources with different key/row shapes.

---

## Season Brackets Variant (Implemented Pattern)

`season_brackets` uses a variant of this template because placeholder rows are
part of normal behavior and completion is season-level, not row-level.

### Scope selector (completion-based)

Instead of a date window, season selection is:

- `all_season_ids` from `sr_seasons`
- minus `completed_season_ids` from `sr_season_brackets` where:
  - `cup_round_id IS NOT NULL`

A season is considered completed once any actual bracket row exists.
Seasons with only placeholder rows (null bracket fields) stay in process scope.

**Code**
- `injestion/core/bq.py`
  - `get_completed_season_ids_from_season_brackets_table(...)`
- `injestion/sportradar/pipelines/season_brackets.py`
  - completion-based filtering logic

### Write model (replace per season on success)

For each successfully fetched season:

1. delete existing rows for that `season_id`
2. insert transformed rows for that season

This model was chosen to:
- replace placeholder/null-only rows with fresh data
- avoid accumulating duplicate placeholder rows

**Code**
- `injestion/core/bq.py`
  - `replace_season_brackets_rows_for_season(...)`

### Retry + failed checkpoint + failed-only rerun

Implemented exactly in the same style as `season_competitors`:

- per-season retries:
  - `SEASON_BRACKETS_MAX_RETRIES = 3`
  - `SEASON_BRACKETS_RETRY_DELAY_SECONDS = 1.0`
- failed ID checkpoint file:
  - `raw_data/sportradar/failed_processes/season_brackets_failed_season_ids.json`
- failed-only override env:
  - `SR_SEASON_BRACKETS_IDS_JSON`
- Makefile toggles:
  - `SR_SEASON_BRACKETS_FAILED_ONLY ?= 0`
  - `SR_SEASON_BRACKETS_FAILED_IDS_JSON ?= raw_data/sportradar/failed_processes/season_brackets_failed_season_ids.json`

### Important caveats

- **Delete-then-insert is not transactional** in current helper:
  - if insert fails after delete, that season can be temporarily empty until rerun.
- **Failed-only overrides bypass completion filter**:
  - if a completed season ID is provided explicitly, it will still be re-fetched and replaced.

### Downstream integration impact

`event_summary` (and therefore `event_statistics` + `event_timeline`) sources
`sport_event_id` from `sr_season_brackets`.

This means season-brackets completeness directly controls event/timeline
ingestion coverage.

