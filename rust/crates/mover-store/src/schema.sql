CREATE TABLE jobs (
    job_id INTEGER PRIMARY KEY AUTOINCREMENT,
    generator_id TEXT NOT NULL,
    submission_id TEXT NOT NULL,
    source_directory TEXT NOT NULL,
    source_root_id TEXT NOT NULL,
    source_root_path TEXT NOT NULL,
    source_relative_directory TEXT NOT NULL,
    destination_id TEXT NOT NULL,
    destination_path TEXT NOT NULL,
    group_by_generator INTEGER NOT NULL CHECK(group_by_generator IN (0,1)),
    delete_source_after_commit INTEGER NOT NULL CHECK(delete_source_after_commit IN (0,1)),
    missing_retry_seconds INTEGER NOT NULL CHECK(missing_retry_seconds BETWEEN 0 AND 4294967295),
    file_count INTEGER NOT NULL CHECK(file_count > 0),
    UNIQUE(generator_id, submission_id)
);
CREATE TABLE files (
    job_id INTEGER NOT NULL REFERENCES jobs(job_id),
    file_index INTEGER NOT NULL CHECK(file_index >= 0),
    relative_path TEXT NOT NULL,
    expected_size TEXT,
    PRIMARY KEY(job_id, file_index),
    UNIQUE(job_id, relative_path)
);
CREATE TABLE reservations (
    source_root_id TEXT NOT NULL,
    source_relative_path TEXT NOT NULL,
    job_id INTEGER NOT NULL,
    file_index INTEGER NOT NULL,
    PRIMARY KEY(source_root_id, source_relative_path),
    FOREIGN KEY(job_id, file_index) REFERENCES files(job_id, file_index)
);
