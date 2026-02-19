# Sport Event Timeline (sport_event_timeline API) – Storage Design

All three sample files come from the same API endpoint but with different **coverage** (`sport_event.coverage.sport_event_properties`). What is returned depends on the match’s coverage, not on a different endpoint.

---

## 1. Coverage-driven differences (summary)

| What | Minimal | Play-by-play (PBP) | Enhanced stats |
|------|--------|--------------------|----------------|
| **coverage.enhanced_stats** | `false` | `false` | `true` |
| **coverage.detailed_serve_outcomes** | `false` | `true` | `true` |
| **coverage.play_by_play** | `false` | `true` | `true` |
| **coverage.scores** | (absent) | `"live"` | `"live"` |
| **Top-level keys** | `generated_at`, `sport_event`, `sport_event_status` | + `statistics`, `timeline` | + `statistics`, `timeline` |
| **statistics** | Not present | Present (basic stats) | Present (basic + stroke-level stats) |
| **timeline** | Not present | Present (full PBP) | Present (same shape as PBP) |

### Always present (all coverage levels)

- **generated_at**
- **sport_event**: id, start_time, sport_event_context (sport, category, competition, season, stage, round, groups, mode), coverage, competitors, venue, channels, estimated
- **sport_event_status**: status, match_status, home_score, away_score, winner_id, period_scores (set scores; can include home_tiebreak_score, away_tiebreak_score)

So every response has enough for “one row per match” (identity, context, result, set scores).

### Present only when coverage includes stats/PBP

- **statistics.totals.competitors[]**: per-competitor stats.  
  - **Basic (PBP)**: aces, breakpoints_won, double_faults, first_serve_points_won, first_serve_successful, games_won, max_games_in_a_row, max_points_in_a_row, points_won, points_won_from_last_10, second_serve_points_won, second_serve_successful, service_games_won, service_points_lost, service_points_won, tiebreaks_won, total_breakpoints (17 keys).  
  - **Enhanced**: all of the above plus backhand_*, forehand_*, groundstroke_*, drop_shot_*, lob_*, overhead_stroke_*, return_*, volley_* (winners/errors/unforced_errors). ~35+ stat keys in total.
- **timeline[]**: ordered list of events.  
  - **Event types**: deciding_team, first_serve, match_started, match_ended, period_start, period_score, point.  
  - **point**: id, type, time, competitor, home_score, away_score, server, result (server_won | receiver_won | ace | double_fault), optional first_serve_fault.  
  - **period_score**: id, type, time, period, home_score, away_score, competitor, server, result, optional first_serve_fault.  
  - **period_start**: period_name (e.g. "1st_set").  
  - Other types have type-specific fields (e.g. competitor for deciding_team, first_serve).

So the only structural difference between PBP and enhanced is **how many statistic keys** exist per competitor; the timeline shape is the same (and point/period_score can already have `result: "ace"` or `"double_fault"` and `first_serve_fault` in both).

---

## 2. Recommended storage approach

### Option A (recommended): Three tables

- **1. Event summary (one row per match)**  
  - One row per `sport_event.id`, always.  
  - Columns: generated_at, sport_event_id, start_time, and flattened fields from sport_event (context: category_id, competition_id, season_id, stage phase/type, round name, mode best_of; competitor ids/names/qualifier; venue id/name/city/country; etc.) and from sport_event_status (status, match_status, home_score, away_score, winner_id).  
  - Optional: store coverage flags (enhanced_stats, detailed_serve_outcomes, play_by_play) so you know what was available for this match.  
  - Set scores can be stored as JSON/STRUCT or normalized (e.g. a small “set_scores” table: event_id, set_number, home_score, away_score, tiebreak_home, tiebreak_away) depending on how you query.

- **2. Match statistics (zero or two rows per match)**  
  - One row per competitor per match, only when `statistics` was present.  
  - Columns: sport_event_id, competitor_id, qualifier (home/away), then **one column per possible stat** (aces, double_faults, first_serve_successful, …, forehand_winners, backhand_errors, volley_winners, etc.).  
  - Use a single wide schema with all ~35 stat columns; for non‑enhanced matches, the “enhanced-only” columns are NULL.  
  - Avoids separate “basic” vs “enhanced” tables and keeps querying simple (e.g. “all matches where we have forehand_winners”) and ingestion uniform (same row shape, fill what the API sent).

- **3. Timeline / play-by-play (zero or N rows per match)**  
  - One row per timeline event when `timeline` was present.  
  - Columns: sport_event_id, event_id (timeline item id), event_order (or infer from order), type, time, and nullable fields used by different types: competitor, period_name, period, home_score, away_score, server, result, first_serve_fault, etc.  
  - One wide table is enough: type-specific fields stay NULL for other types.  
  - Keeps one source of truth for “everything that happened in the match” and allows point-level and set-level analytics.

This gives:

- A single, coverage-invariant event summary.
- A single statistics table that handles both basic and enhanced by using NULL for missing stats.
- A single timeline table for all PBP data.

### Option B: Compress into one table

- **Not recommended.** You would have to store event summary + two blobs (stats per competitor, full timeline) or heavily repeated/denormalized rows. Querying “all matches with enhanced stats” or “point sequences” becomes harder and less efficient than separate statistics and timeline tables.

### Option C: Separate “basic stats” and “enhanced stats” tables

- Possible but redundant: enhanced responses include all basic stats. You’d either duplicate basic stats in two tables or have a confusing split. One wide statistics table with NULLs for unavailable stats is simpler and one place to maintain.

---

## 3. Handling discrepancies in your pipeline

- **Event summary**: Always emit one row; take sport_event + sport_event_status from the payload. If you store coverage flags, set them from `coverage.sport_event_properties`.
- **Statistics**: If `statistics.totals.competitors` exists, emit two rows (home/away). Map every known stat key to a column; if a key is missing for that match (e.g. no enhanced), leave that column NULL.
- **Timeline**: If `timeline` exists, emit one row per event. Map type and all possible fields (competitor, period, home_score, away_score, server, result, first_serve_fault, period_name, etc.) into a fixed schema; leave unused fields NULL.
- **Idempotency**: Use (sport_event_id) for event summary, (sport_event_id, competitor_id) for statistics, (sport_event_id, event_id) for timeline so re-ingestion (e.g. MERGE or overwrite) does not duplicate.

---

## 4. Note on sample file

`sport_event_summary_enhanced_stats.json` was empty (0 bytes) on disk when checked; the structure described above for “enhanced” is taken from an in-memory read of that file (US Open 2025 final – Sinner vs Alcaraz) and from the same API pattern. If your “Australian Open 2026 finals” sample is a different file or you re-save it, the same three-table design still applies: enhanced just adds more stat columns and reuses the same timeline shape.
