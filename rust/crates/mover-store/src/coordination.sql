CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE manifests (
    job_id INTEGER PRIMARY KEY REFERENCES jobs(job_id),
    bytes TEXT NOT NULL CHECK(length(bytes) BETWEEN 1 AND 131072),
    sha256 TEXT NOT NULL CHECK(length(sha256)=64),
    phase INTEGER NOT NULL CHECK(phase BETWEEN 0 AND 4),
    object_identity TEXT,
    CHECK((phase=0 AND object_identity IS NULL) OR (phase>0 AND object_identity IS NOT NULL))
);
CREATE TABLE delivery_failures (
    job_id INTEGER PRIMARY KEY REFERENCES jobs(job_id),
    failures INTEGER NOT NULL CHECK(failures BETWEEN 0 AND 3),
    retry_after INTEGER NOT NULL CHECK(retry_after>=0),
    code TEXT NOT NULL CHECK(code IN ('delivery_requires_review','destination_unavailable'))
);
