CREATE TABLE source_cleanups (
    job_id INTEGER NOT NULL,
    file_index INTEGER NOT NULL CHECK(file_index BETWEEN 0 AND 255),
    state TEXT NOT NULL CHECK(state IN ('Intent','Removed','Failed')),
    authorized INTEGER NOT NULL CHECK(authorized IN (0,1)),
    attempts INTEGER NOT NULL CHECK(attempts >= 0),
    next_attempt_at INTEGER CHECK(next_attempt_at IS NULL OR next_attempt_at >= 0),
    diagnostic TEXT CHECK(diagnostic IS NULL OR (length(diagnostic) BETWEEN 1 AND 240 AND diagnostic NOT GLOB '*[^ -~]*')),
    updated_at INTEGER NOT NULL CHECK(updated_at >= 0),
    PRIMARY KEY(job_id, file_index),
    FOREIGN KEY(job_id, file_index) REFERENCES files(job_id, file_index),
    CHECK(state = 'Failed' OR authorized = 1),
    CHECK((state = 'Failed') = (next_attempt_at IS NOT NULL))
);
