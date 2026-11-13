CREATE TABLE job_problems (
    job_id INTEGER PRIMARY KEY REFERENCES jobs(job_id),
    stage TEXT NOT NULL CHECK(stage IN ('claim','delivery')),
    diagnostic TEXT NOT NULL CHECK(length(diagnostic) BETWEEN 1 AND 240 AND diagnostic NOT GLOB '*[^ -~]*'),
    file_index INTEGER CHECK(file_index IS NULL OR file_index BETWEEN 0 AND 255),
    recorded_at INTEGER NOT NULL CHECK(recorded_at >= 0)
);
