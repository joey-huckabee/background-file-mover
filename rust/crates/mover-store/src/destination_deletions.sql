CREATE TABLE destination_deletion_targets (
    job_id INTEGER NOT NULL REFERENCES jobs(job_id),
    kind TEXT NOT NULL CHECK(kind IN ('UnfinishedDestinationStaging','UnfinishedDestinationPayload','UnfinishedManifestStaging')),
    file_index INTEGER NOT NULL CHECK(file_index BETWEEN -1 AND 255),
    attempt INTEGER NOT NULL CHECK(attempt BETWEEN 0 AND 100),
    pass INTEGER CHECK(pass IS NULL OR pass >= 1),
    state TEXT NOT NULL CHECK(state IN ('Pending','Deleted','Failed')),
    diagnostic TEXT CHECK(diagnostic IS NULL OR (length(diagnostic) BETWEEN 1 AND 240 AND diagnostic NOT GLOB '*[^ -~]*')),
    PRIMARY KEY(job_id, kind, file_index, attempt),
    CHECK((kind = 'UnfinishedManifestStaging') = (file_index = -1 AND attempt = 0)),
    CHECK(kind = 'UnfinishedManifestStaging' OR (file_index >= 0 AND attempt >= 1)),
    CHECK(pass IS NOT NULL OR (kind = 'UnfinishedDestinationStaging' AND state != 'Pending'))
);
