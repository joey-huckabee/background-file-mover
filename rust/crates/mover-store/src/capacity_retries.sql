-- Schema 11: widen only the scheduling classification vocabulary.
-- Keep original counts/deadlines; do not reinterpret existing failure rows.
ALTER TABLE delivery_failures RENAME TO delivery_failures_v10;
CREATE TABLE delivery_failures (
    job_id INTEGER PRIMARY KEY REFERENCES jobs(job_id),
    failures INTEGER NOT NULL CHECK(failures BETWEEN 0 AND 3),
    retry_after INTEGER NOT NULL CHECK(retry_after>=0),
    code TEXT NOT NULL CHECK(code IN ('delivery_requires_review','destination_unavailable','destination_binding_requires_review','destination_capacity_requires_review'))
);
INSERT INTO delivery_failures SELECT * FROM delivery_failures_v10;
DROP TABLE delivery_failures_v10;
