-- Schema 12: the same create/rename/index recipe is used by fresh state and
-- explicit guarded migrations and test fixtures.
CREATE TABLE jobs_v12 (
    job_id INTEGER PRIMARY KEY AUTOINCREMENT,
    generator_id TEXT NOT NULL,
    submission_id TEXT,
    source_directory TEXT NOT NULL,
    source_root_id TEXT NOT NULL,
    source_root_path TEXT NOT NULL,
    source_relative_directory TEXT NOT NULL,
    destination_id TEXT NOT NULL,
    destination_path TEXT NOT NULL,
    group_by_generator INTEGER NOT NULL CHECK(group_by_generator IN (0,1)),
    delete_source_after_commit INTEGER NOT NULL CHECK(delete_source_after_commit IN (0,1)),
    missing_retry_seconds INTEGER NOT NULL CHECK(missing_retry_seconds BETWEEN 0 AND 4294967295),
    file_count INTEGER NOT NULL CHECK(file_count > 0),
    identity_kind INTEGER NOT NULL CHECK(typeof(identity_kind)='integer' AND identity_kind IN (0,1)),
    recording_uuid BLOB,
    request_identity_version INTEGER,
    request_identity_sha256 BLOB,
    CHECK(
        (identity_kind=0 AND submission_id IS NOT NULL AND typeof(submission_id)='text'
         AND recording_uuid IS NULL AND request_identity_version IS NULL
         AND request_identity_sha256 IS NULL)
        OR
        (identity_kind=1 AND submission_id IS NULL
         AND typeof(recording_uuid)='blob' AND length(recording_uuid)=16
         AND request_identity_version IS NOT NULL
         AND typeof(request_identity_version)='integer' AND request_identity_version=1
         AND typeof(request_identity_sha256)='blob' AND length(request_identity_sha256)=32)
    )
);
ALTER TABLE jobs_v12 RENAME TO jobs;
CREATE UNIQUE INDEX jobs_legacy_identity
    ON jobs(generator_id COLLATE BINARY,submission_id COLLATE BINARY)
    WHERE identity_kind=0;
CREATE UNIQUE INDEX jobs_uuid_identity ON jobs(recording_uuid)
    WHERE identity_kind=1;
