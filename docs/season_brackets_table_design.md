# Season brackets: flattened table design

## Raw API shape (per season)

- **No bracket yet** (future/prepped season): `{ "generated_at": "ISO8601" }` — no `stages`.
- **With bracket**: `{ "generated_at": "ISO8601", "stages": [ ... ] }`

Each **stage** has: `order`, `type` (e.g. `"cup"`), `phase` (e.g. `"qualification"`, `"stage_1_playoff"`), `start_date`, `end_date`, `year`, `groups[]`.

Each **group** has: `id` (e.g. `sr:cup:177381`), `group_name`, `cup_rounds[]`.

Each **cup_round** has:

- `id` (e.g. `sr:cup_round:2507684`) — unique round instance (one row per match slot)
- `name` (e.g. `qualification_round_1`, `round_of_128`, `qualification_final`)
- `order` — position within that round name
- `state`, `winner_id` (optional)
- `sport_events[]` — matches in this slot (usually one)
- `linked_cup_rounds[]` — **parent link**: `{ "id": "sr:cup_round:...", "type": "parent", "name": "...", "order": N }`  
  Meaning: “winners of *this* round feed into *that* round.” So **this round is the child**, **linked id is the parent**.

So the hierarchy is: many child round slots → one parent round slot (single-elimination). In the data, each cup_round has zero or one `linked_cup_rounds` entry with `type: "parent"`; the final has none.

---

## Recommended flattened table: one row per round (cup_round)

**Table: `season_bracket_rounds`** (or `sr_season_bracket_rounds`)

| Column | Type | Description |
|--------|------|-------------|
| `season_id` | STRING | e.g. `sr:season:128143` |
| `generated_at` | TIMESTAMP | When we fetched this season’s bracket |
| `stage_order` | INT | Stage order (1, 2, …) |
| `stage_phase` | STRING | e.g. `qualification`, `stage_1_playoff` |
| `stage_type` | STRING | e.g. `cup` |
| `stage_start_date` | DATE | Stage window |
| `stage_end_date` | DATE | Stage window |
| `stage_year` | STRING | e.g. `2026` |
| `group_id` | STRING | e.g. `sr:cup:177381` |
| `group_name` | STRING | e.g. "2026 Australian Open, Melbourne, Australia, Qualifying" |
| `cup_round_id` | STRING | PK for the round slot, e.g. `sr:cup_round:2507684` |
| `round_name` | STRING | e.g. `qualification_round_1`, `round_of_64`, `qualification_final` |
| `round_order` | INT | Order within the round (match index) |
| `parent_cup_round_id` | STRING NULL | The round this feeds into; NULL for finals / no parent |
| `state` | STRING NULL | e.g. `winner` |
| `winner_id` | STRING NULL | e.g. `sr:competitor:108767` |

**Parent–child usage**

- **Child → parent**: `parent_cup_round_id` on each row. “This round’s winner goes to this parent round.”
- **Parent → children**: `SELECT * FROM season_bracket_rounds WHERE parent_cup_round_id = 'sr:cup_round:2507812'`.
- **Roots** (e.g. finals): `parent_cup_round_id IS NULL`.
- **Depth / path**: possible in SQL with recursive CTEs if you need “round 1 → round 2 → … → final”.

**Seasons with no bracket**

- For raw with no `stages`: emit **one row per season** with `season_id`, `generated_at`, and **NULL** for all stage/group/round columns.
- Keeps “we have this season but no structure yet” in the same table; filter with `WHERE cup_round_id IS NOT NULL` for “has bracket”.

**Optional: link table**

If you ever need multiple link types or many-to-many, add a second table:

- **`season_bracket_round_links`**: `season_id`, `child_cup_round_id`, `parent_cup_round_id`, `link_type` (e.g. `parent`), `parent_round_name`, `parent_order`.  
  One row per `linked_cup_rounds` entry. For the current API (single parent per round), the single `parent_cup_round_id` column on `season_bracket_rounds` is enough.

---

## Summary

- **One row per cup_round** (and one row per “no bracket” season) in `season_bracket_rounds`.
- **Parent–child**: `parent_cup_round_id` on the same table; NULL = no parent (e.g. final or no bracket).
- **Future seasons**: same table, one row per season with round columns NULL.
