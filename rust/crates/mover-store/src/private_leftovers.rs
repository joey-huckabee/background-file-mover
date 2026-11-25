//! Durable, informational directory-leftover observations. No deletion authority.
use super::*;

pub const PRIVATE_LEFTOVERS: &str = "unexpected_private_leftovers";

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PrivateLeftover {
    pub file_index: usize,
    pub folder_path: String,
}

/// Reuse per-file success diagnostics in schema 18. Existing state/deletion
/// semantics do not depend on a successful row's diagnostic being NULL.
/// The path is already durable in the claim; never store unknown entry names.
pub(super) fn view(c: &Connection, job_id: i64) -> Result<Vec<PrivateLeftover>> {
    let mut indices = std::collections::BTreeSet::new();
    for (table, state) in [
        ("source_cleanups", "Removed"),
        ("deletion_targets", "Deleted"),
    ] {
        let exists: bool = c.query_row(
            "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name=?1)",
            [table],
            |r| r.get(0),
        )?;
        if !exists {
            continue;
        }
        let sql = match table {
            "source_cleanups" => {
                "SELECT file_index FROM source_cleanups WHERE job_id=?1 AND state=?2 AND diagnostic=?3"
            }
            _ => {
                "SELECT file_index FROM deletion_targets WHERE job_id=?1 AND state=?2 AND diagnostic=?3 AND kind='RetainedSource'"
            }
        };
        let mut statement = c.prepare(sql)?;
        for index in statement.query_map(params![job_id, state, PRIVATE_LEFTOVERS], |r| {
            r.get::<_, i64>(0)
        })? {
            indices.insert(index?);
        }
    }
    indices
        .into_iter()
        .map(|index| {
            let index = usize::try_from(index).map_err(|_| StoreError::CorruptState)?;
            let (intent, done) = load_claim(c, job_id, index)?.ok_or(StoreError::CorruptState)?;
            if !done {
                return Err(StoreError::CorruptState);
            }
            // The canonical root plus the service-owned suffix can exceed the
            // maximum producer path length. This is display-only, never reopened.
            let path = format!("{}/.file-mover/{}", intent.root_path, intent.private_name);
            if path.len() > 8192 {
                return Err(StoreError::CorruptState);
            }
            Ok(PrivateLeftover {
                file_index: index,
                folder_path: path,
            })
        })
        .collect()
}
