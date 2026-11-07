CREATE TABLE source_ownership (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    receipt TEXT NOT NULL CHECK(length(receipt) BETWEEN 1 AND 8192),
    object TEXT CHECK(length(object) BETWEEN 1 AND 512)
);
