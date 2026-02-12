# Category filter guide (sr_competitions.json)

Use this when filtering **competitions** or **seasons** (e.g. in `sr_seasons.json`, join on `competition_id` to competition and then filter by category). Goal: keep only the main professional circuits where the biggest players participate.

---

## Categories to INCLUDE (focus on these)

Filter competitions where **`category.id`** is one of:

| category.id   | category.name        | What it is |
|---------------|----------------------|------------|
| **sr:category:3**  | ATP                  | Men's tour: Grand Slams, Masters 1000, 500s, 250s, ATP Finals, Olympics (men), etc. |
| **sr:category:6**  | WTA                  | Women's tour: Grand Slams, WTA 1000/500/250, WTA Finals, Olympics (women), etc. |
| **sr:category:76** | Davis Cup            | Men's national team competition (1 competition) |
| **sr:category:74** | Billie Jean King Cup | Women's national team competition (1 competition) |

**Recommended filter (SQL-like):**
```text
WHERE category.id IN (
  'sr:category:3',   -- ATP
  'sr:category:6',   -- WTA
  'sr:category:76',  -- Davis Cup
  'sr:category:74'   -- Billie Jean King Cup
)
```

When joining **seasons** (e.g. from `sr_seasons.json`): keep only seasons whose `competition_id` appears in the competitions list after applying the category filter above.

---

## Optional: restrict by competition level (ATP/WTA only)

If you want only the **biggest** events (no 250s, no Next Gen, etc.), you can additionally filter on **`level`** for ATP and WTA:

**ATP levels to include (top tiers):**
- `grand_slam`
- `atp_1000`
- `atp_500`
- `atp_world_tour_finals`

**ATP levels to exclude (if narrowing scope):**
- `atp_250` (smaller events)
- `atp_next_generation` (Next Gen ATP Finals only)

**WTA levels to include (top tiers):**
- `grand_slam`
- `wta_1000`
- `wta_500`
- `wta_championships` (WTA Finals)

**WTA levels to exclude (if narrowing scope):**
- `wta_250`
- `wta_international` / `wta_premier` (legacy tiers)
- `wta_elite_trophy`

Davis Cup and Billie Jean King Cup do not have a `level` in this file; include them by category only.

---

## Categories to EXCLUDE (do not use for “big players” focus)

These are in **sr_competitions.json** but are not the main ATP/WTA/team circuits:

| category.id      | category.name         | Why exclude |
|-----------------|------------------------|-------------|
| sr:category:785 | ITF Men                | Lower-tier pro (Futures, etc.) |
| sr:category:213 | ITF Women              | Lower-tier pro |
| sr:category:72  | Challenger             | ATP Challenger / development tier |
| sr:category:871 | WTA 125K               | WTA secondary tier |
| sr:category:2516| UTR Men                | UTR/amateur |
| sr:category:2517| UTR Women              | UTR/amateur |
| sr:category:79  | Exhibition             | Exhibitions, not official tour |
| sr:category:1474| Juniors                | Junior slams/events |
| sr:category:1476| Wheelchairs            | Wheelchair slams/events |
| sr:category:1475| Legends                | Legends exhibitions |
| sr:category:2400| Wheelchairs Juniors    | Wheelchair juniors |
| sr:category:181 | Hopman Cup             | Mixed exhibition (optional: include if you want) |
| sr:category:1012| IPTL                   | Defunct league |
| sr:category:2414| United Cup             | Mixed team event (optional: include if you want) |

---

## Summary for your data engineer

1. **Seasons:** From `sr_seasons.json`, keep seasons where `competition_id` belongs to a competition (from `sr_competitions.json`) with  
   `category.id IN ('sr:category:3', 'sr:category:6', 'sr:category:76', 'sr:category:74')`.

2. **Competitions:** From `sr_competitions.json`, keep rows with that same `category.id` list.

3. **Optional:** To restrict to top-tier events only, also filter ATP/WTA competitions by `level` (e.g. only `grand_slam`, `atp_1000`, `atp_500`, `atp_world_tour_finals`, `wta_1000`, `wta_500`, `wta_championships`).

4. **Olympics:** Olympic tennis is under **ATP** (Men Singles/Doubles, Mixed) and **WTA** (Women Singles/Doubles) in this feed, so no extra category is needed.
