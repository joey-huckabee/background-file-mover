CREATE TABLE missing_resets (
    job_id INTEGER NOT NULL,
    command_id TEXT NOT NULL CHECK(length(command_id) BETWEEN 1 AND 128),
    review_epoch INTEGER NOT NULL CHECK(review_epoch BETWEEN 0 AND 63),
    file_index INTEGER NOT NULL,
    actor TEXT NOT NULL CHECK(length(actor) BETWEEN 1 AND 128),
    reason TEXT NOT NULL CHECK(length(reason) BETWEEN 1 AND 512),
    recorded_at INTEGER NOT NULL CHECK(recorded_at>=0),
    prior_deadline INTEGER NOT NULL CHECK(prior_deadline>=0),
    prior_blocked INTEGER NOT NULL CHECK(prior_blocked IN (0,1)),
    new_deadline INTEGER NOT NULL CHECK(new_deadline>recorded_at),
    retry_window_seconds INTEGER NOT NULL CHECK(retry_window_seconds BETWEEN 1 AND 86400),
    PRIMARY KEY(job_id,command_id),
    UNIQUE(job_id,review_epoch),
    FOREIGN KEY(job_id,file_index) REFERENCES files(job_id,file_index)
);
