CREATE TABLE retry_contexts (
    job_id INTEGER NOT NULL REFERENCES jobs(job_id),
    context_key TEXT NOT NULL CHECK(length(context_key)=64),
    principal TEXT NOT NULL CHECK(length(principal) BETWEEN 1 AND 128),
    instance_id TEXT NOT NULL CHECK(length(instance_id)=32),
    review_epoch INTEGER NOT NULL CHECK(review_epoch BETWEEN 0 AND 4294967295),
    reason TEXT NOT NULL CHECK(length(CAST(reason AS BLOB)) BETWEEN 1 AND 512),
    PRIMARY KEY(job_id,context_key)
);
CREATE TABLE retry_outcomes (
    job_id INTEGER NOT NULL,
    context_key TEXT NOT NULL,
    occurrence INTEGER NOT NULL CHECK(occurrence BETWEEN 0 AND 255),
    outcome TEXT NOT NULL CHECK(outcome IN ('accepted','failed','skipped')),
    PRIMARY KEY(job_id,context_key,occurrence),
    FOREIGN KEY(job_id,context_key) REFERENCES retry_contexts(job_id,context_key)
);
