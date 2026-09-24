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

