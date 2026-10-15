CREATE TABLE source_enrollment (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    source_path TEXT NOT NULL CHECK(length(source_path) BETWEEN 2 AND 8192),
    binding TEXT NOT NULL CHECK(length(binding) BETWEEN 1 AND 4096),
    observation TEXT NOT NULL CHECK(length(observation) BETWEEN 1 AND 2048),
    state_instance_id TEXT NOT NULL CHECK(length(state_instance_id)=32)
);
