CREATE TABLE missing (
    job_id INTEGER NOT NULL,
    file_index INTEGER NOT NULL,
    deadline INTEGER NOT NULL CHECK(deadline >= 0),
    blocked INTEGER NOT NULL DEFAULT 0 CHECK(blocked IN (0,1)),
    PRIMARY KEY(job_id,file_index),
    FOREIGN KEY(job_id,file_index) REFERENCES files(job_id,file_index)
);
