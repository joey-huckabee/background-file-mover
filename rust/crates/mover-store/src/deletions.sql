CREATE TABLE deletion_passes (
    job_id INTEGER PRIMARY KEY REFERENCES jobs(job_id),
    pass INTEGER NOT NULL CHECK(pass >= 1),
    state TEXT NOT NULL CHECK(state IN ('Active','Done')),
    principal TEXT NOT NULL CHECK(length(principal) BETWEEN 1 AND 128),
    proof_digest TEXT NOT NULL CHECK(length(proof_digest) = 64),
    requested_at INTEGER NOT NULL CHECK(requested_at >= 0),
    finished_at INTEGER CHECK(finished_at IS NULL OR finished_at >= requested_at),
    CHECK((state = 'Active') = (finished_at IS NULL))
);
CREATE TABLE deletion_targets (
    job_id INTEGER NOT NULL REFERENCES deletion_passes(job_id),
    file_index INTEGER NOT NULL CHECK(file_index BETWEEN 0 AND 255),
    kind TEXT NOT NULL CHECK(kind IN ('RetainedSource','UnfinishedDestinationStaging','UnfinishedDestinationPayload','UnfinishedManifestStaging')),
    pass INTEGER NOT NULL CHECK(pass >= 1),
    state TEXT NOT NULL CHECK(state IN ('Pending','Deleted','Failed')),
    diagnostic TEXT CHECK(diagnostic IS NULL OR (length(diagnostic) BETWEEN 1 AND 240 AND diagnostic NOT GLOB '*[^ -~]*')),
    PRIMARY KEY(job_id, file_index, kind)
);
