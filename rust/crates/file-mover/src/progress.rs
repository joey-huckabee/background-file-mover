//! Live transfer progress for the dashboard, in memory only (never persisted).
//! Delivery sessions feed it from their children's advisory progress channel
//! (`mover_fs::ProgressSender`); the admin event stream reads a snapshot about
//! every 2 seconds while transfers are active. Nothing here is on the copy
//! path: the coordinator drains updates while it waits for a step's reply.
//!
//! Entries are per file, because one job can copy several files at once
//! (`delivery_file_concurrency`); the snapshot reports one row per job.
use mover_fs::{ProgressPhase, ProgressUpdate};
use std::{
    collections::BTreeMap,
    sync::{LazyLock, Mutex},
    time::{Duration, Instant},
};

/// A transfer with no update for this long shows 0 B/s (for example blocked I/O).
const STALE: Duration = Duration::from_secs(5);
/// Shortest sample spacing used for a speed estimate.
const MIN_SAMPLE: Duration = Duration::from_millis(250);

struct Entry {
    files: usize,
    update: ProgressUpdate,
    updated: Instant,
    /// Start of the current speed sample: (time, bytes, phase).
    sample: (Instant, u64, ProgressPhase),
    bytes_per_second: f64,
}
impl Entry {
    /// The file's verification has read every byte: nothing more to report.
    fn finished(&self) -> bool {
        self.update.phase == ProgressPhase::Verifying && self.update.done == self.update.total
    }
    fn rate(&self, now: Instant) -> u64 {
        if now.duration_since(self.updated) > STALE {
            0
        } else {
            self.bytes_per_second.max(0.0) as u64
        }
    }
}

#[derive(Default)]
pub(crate) struct Board(Mutex<BTreeMap<(i64, u32), Entry>>);
pub(crate) static BOARD: LazyLock<Board> = LazyLock::new(Board::default);

impl Board {
    fn entries(&self) -> std::sync::MutexGuard<'_, BTreeMap<(i64, u32), Entry>> {
        self.0.lock().unwrap_or_else(|e| e.into_inner())
    }
    pub(crate) fn update(&self, job: i64, files: usize, u: ProgressUpdate) {
        self.update_at(job, files, u, Instant::now());
    }
    fn update_at(&self, job: i64, files: usize, u: ProgressUpdate, now: Instant) {
        let mut entries = self.entries();
        let entry = entries.entry((job, u.file_index)).or_insert_with(|| Entry {
            files,
            update: u,
            updated: now,
            sample: (now, u.done, u.phase),
            bytes_per_second: 0.0,
        });
        let (at, bytes, phase) = entry.sample;
        if phase != u.phase || u.done < bytes {
            // A new phase: restart the sample, keep the last speed.
            entry.sample = (now, u.done, u.phase);
        } else if now.duration_since(at) >= MIN_SAMPLE {
            let rate = (u.done - bytes) as f64 / now.duration_since(at).as_secs_f64();
            entry.bytes_per_second = if entry.bytes_per_second == 0.0 {
                rate
            } else {
                0.5 * entry.bytes_per_second + 0.5 * rate
            };
            entry.sample = (now, u.done, u.phase);
        }
        entry.files = files;
        entry.update = u;
        entry.updated = now;
    }
    pub(crate) fn remove(&self, job: i64) {
        self.entries().retain(|(j, _), _| *j != job);
    }
    #[cfg(test)]
    pub(crate) fn is_empty(&self) -> bool {
        self.entries().is_empty()
    }
    /// JSON for the dashboard, one row per job. Integers are strings (lossless
    /// in the browser). A job's row covers its files still in progress (their
    /// bytes and speeds added up); when none is, its most recent file.
    pub(crate) fn snapshot(&self) -> serde_json::Value {
        self.snapshot_at(Instant::now())
    }
    fn snapshot_at(&self, now: Instant) -> serde_json::Value {
        let entries = self.entries();
        let mut jobs: BTreeMap<i64, Vec<&Entry>> = BTreeMap::new();
        for ((job, _), e) in entries.iter() {
            jobs.entry(*job).or_default().push(e);
        }
        let mut total = 0_u64;
        let transfers: Vec<_> = jobs
            .into_iter()
            .map(|(job, files)| {
                let mut active: Vec<&Entry> =
                    files.iter().copied().filter(|e| !e.finished()).collect();
                if active.is_empty() {
                    active = files
                        .iter()
                        .copied()
                        .max_by_key(|e| e.updated)
                        .into_iter()
                        .collect();
                }
                let first = active[0];
                let rate = active
                    .iter()
                    .fold(0_u64, |s, e| s.saturating_add(e.rate(now)));
                let done = active
                    .iter()
                    .fold(0_u64, |s, e| s.saturating_add(e.update.done));
                let size = active
                    .iter()
                    .fold(0_u64, |s, e| s.saturating_add(e.update.total));
                total = total.saturating_add(rate);
                serde_json::json!({
                    "job_id": job.to_string(),
                    "file_id": first.update.file_index.to_string(),
                    "file_count": first.files.to_string(),
                    "active_files": active.len().to_string(),
                    "phase": match first.update.phase {
                        ProgressPhase::Copying => "copying",
                        ProgressPhase::Verifying => "verifying",
                    },
                    "bytes_done": done.to_string(),
                    "bytes_total": size.to_string(),
                    "bytes_per_second": rate.to_string(),
                })
            })
            .collect();
        serde_json::json!({"transfers": transfers, "bytes_per_second": total.to_string()})
    }
}

/// Removes a job's live entries when its delivery attempt ends.
pub(crate) struct Tracked(pub(crate) i64);
impl Drop for Tracked {
    fn drop(&mut self) {
        BOARD.remove(self.0);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn u(file: u32, phase: ProgressPhase, done: u64) -> ProgressUpdate {
        ProgressUpdate {
            file_index: file,
            phase,
            done,
            total: 1 << 30,
        }
    }
    #[test]
    fn speed_is_estimated_per_file_and_phase_and_goes_stale() {
        let b = Board::default();
        let t0 = Instant::now();
        let at = |s| t0 + Duration::from_secs(s);
        b.update_at(7, 2, u(0, ProgressPhase::Copying, 0), t0);
        b.update_at(7, 2, u(0, ProgressPhase::Copying, 100 << 20), at(1));
        let s = b.snapshot_at(at(1));
        assert_eq!(
            s["transfers"][0]["bytes_per_second"],
            (100u64 << 20).to_string()
        );
        assert_eq!(s["bytes_per_second"], (100u64 << 20).to_string());
        assert_eq!(s["transfers"][0]["phase"], "copying");
        assert_eq!(s["transfers"][0]["file_count"], "2");
        assert_eq!(s["transfers"][0]["active_files"], "1");
        // A new phase restarts the sample but keeps the last speed meanwhile.
        b.update_at(7, 2, u(0, ProgressPhase::Verifying, 0), at(2));
        let s = b.snapshot_at(at(2));
        assert_eq!(s["transfers"][0]["phase"], "verifying");
        assert_eq!(
            s["transfers"][0]["bytes_per_second"],
            (100u64 << 20).to_string()
        );
        // Smoothed: 0.5 * 100 MiB/s + 0.5 * 200 MiB/s.
        b.update_at(7, 2, u(0, ProgressPhase::Verifying, 200 << 20), at(3));
        let s = b.snapshot_at(at(3));
        assert_eq!(
            s["transfers"][0]["bytes_per_second"],
            (150u64 << 20).to_string()
        );
        // No update for longer than STALE: shown as 0 B/s, still listed.
        let s = b.snapshot_at(at(9));
        assert_eq!(s["transfers"][0]["bytes_per_second"], "0");
        assert_eq!(s["bytes_per_second"], "0");
        b.remove(7);
        assert!(b.is_empty());
        assert_eq!(b.snapshot()["transfers"].as_array().unwrap().len(), 0);
    }
    #[test]
    fn files_of_one_job_add_up_and_finished_files_drop_out() {
        let b = Board::default();
        let t0 = Instant::now();
        let at = |s| t0 + Duration::from_secs(s);
        for file in 0..3 {
            b.update_at(9, 6, u(file, ProgressPhase::Copying, 0), t0);
            b.update_at(9, 6, u(file, ProgressPhase::Copying, 50 << 20), at(1));
        }
        b.update_at(4, 1, u(0, ProgressPhase::Copying, 0), t0);
        let s = b.snapshot_at(at(1));
        let rows = s["transfers"].as_array().unwrap();
        assert_eq!(rows.len(), 2, "one row per job");
        let job9 = rows.iter().find(|r| r["job_id"] == "9").unwrap();
        assert_eq!(job9["active_files"], "3");
        assert_eq!(job9["bytes_done"], (150u64 << 20).to_string());
        assert_eq!(job9["bytes_total"], (3u64 << 30).to_string());
        assert_eq!(job9["bytes_per_second"], (150u64 << 20).to_string());
        assert_eq!(s["bytes_per_second"], (150u64 << 20).to_string());
        // File 0 fully verified: it no longer counts as in progress.
        b.update_at(9, 6, u(0, ProgressPhase::Verifying, 1 << 30), at(2));
        let s = b.snapshot_at(at(2));
        let job9 = s["transfers"]
            .as_array()
            .unwrap()
            .iter()
            .find(|r| r["job_id"] == "9")
            .unwrap()
            .clone();
        assert_eq!(job9["active_files"], "2");
        assert_eq!(job9["bytes_done"], (100u64 << 20).to_string());
        // Every file finished: the most recent one still shows (not an empty row).
        for file in 1..3 {
            b.update_at(9, 6, u(file, ProgressPhase::Verifying, 1 << 30), at(3));
        }
        let s = b.snapshot_at(at(3));
        let job9 = s["transfers"]
            .as_array()
            .unwrap()
            .iter()
            .find(|r| r["job_id"] == "9")
            .unwrap()
            .clone();
        assert_eq!(job9["active_files"], "1");
        assert_eq!(job9["phase"], "verifying");
        b.remove(9);
        assert_eq!(
            b.snapshot_at(at(3))["transfers"].as_array().unwrap().len(),
            1
        );
    }
}
