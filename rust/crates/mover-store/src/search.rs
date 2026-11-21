//! Admin file-name search: one bounded chunk of a newest-first scan of the
//! jobs' file relative paths (docs/dashboard/FILE-NAME-SEARCH-DESIGN.md).
use super::*;

/// A chunk stops at the next job boundary once it has read this many rows...
pub const SEARCH_CHUNK_ROWS: usize = 8192;
/// ...or this many bytes of path text.
pub const SEARCH_CHUNK_BYTES: usize = 1 << 20;

/// One bounded chunk of a file-name search.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FileSearchChunk {
    /// Matching jobs in this chunk, newest first, distinct.
    pub matches: Vec<i64>,
    /// Jobs scanned whole by this chunk.
    pub scanned_jobs: u32,
    /// The oldest job scanned whole, when more jobs may remain at or above
    /// `until`; `None` when the scan is complete.
    pub continue_before: Option<i64>,
}

impl Store {
    /// Scan jobs with `until <= job_id < before`, newest first, for a file whose
    /// lowercased relative path contains `needle` (already normalized).
    pub fn search_file_paths(
        &self,
        needle: String,
        before: i64,
        until: i64,
    ) -> Result<FileSearchChunk> {
        self.search_file_paths_bounded(needle, before, until, SEARCH_CHUNK_ROWS, SEARCH_CHUNK_BYTES)
    }

    pub(crate) fn search_file_paths_bounded(
        &self,
        needle: String,
        before: i64,
        until: i64,
        max_rows: usize,
        max_bytes: usize,
    ) -> Result<FileSearchChunk> {
        if needle.is_empty() || until < 0 || before <= until {
            return Err(StoreError::InvalidContext);
        }
        self.call(move |db| {
            let tx = db.connection.transaction()?;
            let chunk = scan(&tx, &needle, before, until, max_rows, max_bytes)?;
            tx.commit()?;
            Ok(chunk)
        })
    }
}

/// Reverse primary-key order: SQLite walks the index backwards, never sorts.
pub(crate) const SEARCH_SQL: &str = "SELECT job_id, length(CAST(relative_path AS BLOB)), relative_path \
     FROM files WHERE job_id < ?1 AND job_id >= ?2 ORDER BY job_id DESC, file_index DESC";

fn scan(
    tx: &Connection,
    needle: &str,
    before: i64,
    until: i64,
    max_rows: usize,
    max_bytes: usize,
) -> Result<FileSearchChunk> {
    let mut statement = tx.prepare(SEARCH_SQL)?;
    let mut rows = statement.query(params![before, until])?;
    let (mut matches, mut scanned_jobs) = (Vec::new(), 0u32);
    let (mut read_rows, mut read_bytes) = (0usize, 0usize);
    let mut current: Option<(i64, bool)> = None;
    while let Some(row) = rows.next()? {
        let job: i64 = row.get(0)?;
        if current.is_none_or(|(id, _)| id != job) {
            if let Some((previous, _)) = current {
                scanned_jobs += 1;
                // Stop only between jobs: a job is always scanned whole.
                if read_rows >= max_rows || read_bytes >= max_bytes {
                    return Ok(FileSearchChunk {
                        matches,
                        scanned_jobs,
                        // Jobs below `until` are out of range.
                        continue_before: (previous > until).then_some(previous),
                    });
                }
            }
            current = Some((job, false));
        }
        read_rows += 1;
        let Some((_, matched)) = current.as_mut() else {
            unreachable!("current job set above");
        };
        if *matched {
            continue; // The job already matched: skip its remaining paths.
        }
        // The length is read before the text.
        let length: i64 = row.get(1)?;
        read_bytes += usize::try_from(length).map_err(|_| StoreError::CorruptState)?;
        let path = row
            .get_ref(2)?
            .as_str()
            .map_err(|_| StoreError::CorruptState)?;
        if path.to_lowercase().contains(needle) {
            *matched = true;
            matches.push(job);
        }
    }
    if current.is_some() {
        scanned_jobs += 1;
    }
    Ok(FileSearchChunk {
        matches,
        scanned_jobs,
        continue_before: None,
    })
}
