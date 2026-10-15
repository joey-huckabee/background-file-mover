CREATE TABLE destination_bindings (
    job_id INTEGER PRIMARY KEY REFERENCES jobs(job_id),
    binding TEXT NOT NULL CHECK(length(binding) BETWEEN 1 AND 4096),
    observation TEXT CHECK(observation IS NULL OR length(observation) BETWEEN 1 AND 2048)
);
-- Widen the constrained diagnostic vocabulary while preserving prior retries.
ALTER TABLE delivery_failures RENAME TO delivery_failures_v8;
CREATE TABLE delivery_failures (
    job_id INTEGER PRIMARY KEY REFERENCES jobs(job_id),
    failures INTEGER NOT NULL CHECK(failures BETWEEN 0 AND 3),
    retry_after INTEGER NOT NULL CHECK(retry_after>=0),
    code TEXT NOT NULL CHECK(code IN ('delivery_requires_review','destination_unavailable','destination_binding_requires_review'))
);
INSERT INTO delivery_failures SELECT * FROM delivery_failures_v8;
DROP TABLE delivery_failures_v8;
