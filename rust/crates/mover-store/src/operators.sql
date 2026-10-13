CREATE TABLE operator_resumes (
    job_id INTEGER NOT NULL REFERENCES jobs(job_id),
    command_id TEXT NOT NULL CHECK(length(command_id) BETWEEN 1 AND 128),
    review_epoch INTEGER NOT NULL CHECK(review_epoch BETWEEN 0 AND 63),
    actor TEXT NOT NULL CHECK(length(actor) BETWEEN 1 AND 128),
    reason TEXT NOT NULL CHECK(length(reason) BETWEEN 1 AND 512),
    recorded_at INTEGER NOT NULL CHECK(recorded_at>=0),
    prior_retry_after INTEGER NOT NULL CHECK(prior_retry_after>=0),
    prior_code TEXT NOT NULL,
    PRIMARY KEY(job_id,command_id),
    UNIQUE(job_id,review_epoch)
);
