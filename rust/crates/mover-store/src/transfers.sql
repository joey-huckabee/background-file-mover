CREATE TABLE transfers (
    job_id INTEGER NOT NULL,
    file_index INTEGER NOT NULL,
    attempt INTEGER NOT NULL CHECK(attempt BETWEEN 1 AND 100),
    destination_root TEXT NOT NULL,
    relative_name TEXT NOT NULL,
    root_identity TEXT NOT NULL,
    area_identity TEXT NOT NULL,
    parent_identity TEXT NOT NULL,
    staging_directory_identity TEXT NOT NULL,
    stage_identity TEXT NOT NULL,
    sha256 TEXT,
    phase INTEGER NOT NULL CHECK(phase BETWEEN 0 AND 4),
    PRIMARY KEY(job_id,file_index,attempt),
    FOREIGN KEY(job_id,file_index) REFERENCES files(job_id,file_index),
    CHECK((phase=0 AND sha256 IS NULL) OR (phase>0 AND length(sha256)=64))
);
