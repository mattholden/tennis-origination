-- Reference DDL: Sportradar competitions (flattened from API).
-- Filter by category_id IN ('sr:category:3', 'sr:category:6', 'sr:category:76', 'sr:category:74')
-- for ATP, WTA, Davis Cup, Billie Jean King Cup. See bigquery/category_filter_guide.md.

CREATE TABLE IF NOT EXISTS sr_competitions (
    id              VARCHAR(64) NOT NULL PRIMARY KEY,
    name            VARCHAR(512),
    type            VARCHAR(32),
    gender          VARCHAR(32),
    category_id      VARCHAR(64),
    category_name    VARCHAR(128),
    level           VARCHAR(64),
    parent_id       VARCHAR(64),
    generated_at    TIMESTAMP
);
