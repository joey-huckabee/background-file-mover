CREATE TABLE cancellations (
    job_id INTEGER PRIMARY KEY REFERENCES jobs(job_id),
    state TEXT NOT NULL CHECK(state IN ('Pending','Cancelled')),
    principal TEXT NOT NULL CHECK(length(principal) BETWEEN 1 AND 128),
    requested_at INTEGER NOT NULL CHECK(requested_at >= 0),
    stopped_at INTEGER CHECK(stopped_at IS NULL OR stopped_at >= requested_at),
    CHECK((state = 'Pending') = (stopped_at IS NULL))
);
