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
