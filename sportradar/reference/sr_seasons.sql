-- Reference DDL: Sportradar seasons (flattened from API).
-- Keep only seasons whose competition_id exists in sr_competitions (after category filter).
-- See bigquery/category_filter_guide.md.

CREATE TABLE IF NOT EXISTS sr_seasons (
    id              VARCHAR(64) NOT NULL PRIMARY KEY,
    name            VARCHAR(512),
    start_date      DATE,
    end_date        DATE,
    year            VARCHAR(8),
    competition_id  VARCHAR(64),
    generated_at    TIMESTAMP
);

-- Optional: foreign key to competitions (if both tables in same DB)
-- ALTER TABLE sr_seasons ADD CONSTRAINT fk_sr_seasons_competition
--     FOREIGN KEY (competition_id) REFERENCES sr_competitions(id);
