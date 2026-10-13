CREATE TABLE claims (
    job_id INTEGER NOT NULL,
    file_index INTEGER NOT NULL,
    root_path TEXT NOT NULL,
    source_name TEXT NOT NULL,
    private_name TEXT NOT NULL UNIQUE,
    root_identity TEXT NOT NULL,
    parent_identity TEXT NOT NULL,
    area_identity TEXT NOT NULL,
    source_identity TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0 CHECK(done IN (0,1)),
    PRIMARY KEY(job_id,file_index),
    FOREIGN KEY(job_id,file_index) REFERENCES files(job_id,file_index)
);
