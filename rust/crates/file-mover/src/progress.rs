//! Live transfer progress for the dashboard, in memory only (never persisted).
//! Delivery sessions feed it from their children's advisory progress channel
//! (`mover_fs::ProgressSender`); the admin event stream reads a snapshot about
//! every 2 seconds while transfers are active. Nothing here is on the copy
//! path: the coordinator drains updates while it waits for a step's reply.
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
    /// Start of the current speed sample: (time, bytes, file, phase).
    sample: (Instant, u64, u32, ProgressPhase),
    bytes_per_second: f64,
}

#[derive(Default)]
pub(crate) struct Board(Mutex<BTreeMap<i64, Entry>>);
pub(crate) static BOARD: LazyLock<Board> = LazyLock::new(Board::default);

impl Board {
    fn entries(&self) -> std::sync::MutexGuard<'_, BTreeMap<i64, Entry>> {
        self.0.lock().unwrap_or_else(|e| e.into_inner())
    }
    pub(crate) fn update(&self, job: i64, files: usize, u: ProgressUpdate) {
        self.update_at(job, files, u, Instant::now());
    }
    fn update_at(&self, job: i64, files: usize, u: ProgressUpdate, now: Instant) {
        let mut entries = self.entries();
        let entry = entries.entry(job).or_insert_with(|| Entry {
            files,
            update: u,
            updated: now,
            sample: (now, u.done, u.file_index, u.phase),
            bytes_per_second: 0.0,
        });
        let (at, bytes, file, phase) = entry.sample;
        if file != u.file_index || phase != u.phase || u.done < bytes {
            // A new file or phase: restart the sample, keep the last speed.
            entry.sample = (now, u.done, u.file_index, u.phase);
        } else if now.duration_since(at) >= MIN_SAMPLE {
            let rate = (u.done - bytes) as f64 / now.duration_since(at).as_secs_f64();
            entry.bytes_per_second = if entry.bytes_per_second == 0.0 {
                rate
            } else {
                0.5 * entry.bytes_per_second + 0.5 * rate
            };
            entry.sample = (now, u.done, u.file_index, u.phase);
        }
        entry.files = files;
        entry.update = u;
        entry.updated = now;
    }
    pub(crate) fn remove(&self, job: i64) {
        self.entries().remove(&job);
    }
    #[cfg(test)]
    pub(crate) fn is_empty(&self) -> bool {
        self.entries().is_empty()
    }
    /// JSON for the dashboard. Integers are strings (lossless in the browser).
    pub(crate) fn snapshot(&self) -> serde_json::Value {
        self.snapshot_at(Instant::now())
    }
    fn snapshot_at(&self, now: Instant) -> serde_json::Value {
        let entries = self.entries();
        let mut total = 0_u64;
        let transfers: Vec<_> = entries
            .iter()
            .map(|(job, e)| {
                let rate = if now.duration_since(e.updated) > STALE {
                    0
                } else {
                    e.bytes_per_second.max(0.0) as u64
                };
                total = total.saturating_add(rate);
                serde_json::json!({
                    "job_id": job.to_string(),
                    "file_id": e.update.file_index.to_string(),
                    "file_count": e.files.to_string(),
                    "phase": match e.update.phase {
                        ProgressPhase::Copying => "copying",
                        ProgressPhase::Verifying => "verifying",
                    },
                    "bytes_done": e.update.done.to_string(),
                    "bytes_total": e.update.total.to_string(),
                    "bytes_per_second": rate.to_string(),
                })
            })
            .collect();
        serde_json::json!({"transfers": transfers, "bytes_per_second": total.to_string()})
    }
}

/// Removes a job's live entry when its delivery attempt ends.
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
        b.update_at(7, 2, u(0, ProgressPhase::Copying, 0), t0);
        b.update_at(
            7,
            2,
            u(0, ProgressPhase::Copying, 100 << 20),
            t0 + Duration::from_secs(1),
        );
        let s = b.snapshot_at(t0 + Duration::from_secs(1));
        assert_eq!(
            s["transfers"][0]["bytes_per_second"],
            (100u64 << 20).to_string()
        );
        assert_eq!(s["bytes_per_second"], (100u64 << 20).to_string());
        assert_eq!(s["transfers"][0]["phase"], "copying");
        assert_eq!(s["transfers"][0]["file_count"], "2");
        // A new phase restarts the sample but keeps the last speed meanwhile.
        b.update_at(
            7,
            2,
            u(0, ProgressPhase::Verifying, 0),
            t0 + Duration::from_secs(2),
        );
        let s = b.snapshot_at(t0 + Duration::from_secs(2));
        assert_eq!(s["transfers"][0]["phase"], "verifying");
        assert_eq!(
            s["transfers"][0]["bytes_per_second"],
            (100u64 << 20).to_string()
        );
        // Smoothed: 0.5 * 100 MiB/s + 0.5 * 200 MiB/s.
        b.update_at(
            7,
            2,
            u(0, ProgressPhase::Verifying, 200 << 20),
            t0 + Duration::from_secs(3),
        );
        let s = b.snapshot_at(t0 + Duration::from_secs(3));
        assert_eq!(
            s["transfers"][0]["bytes_per_second"],
            (150u64 << 20).to_string()
        );
        // No update for longer than STALE: shown as 0 B/s, still listed.
        let s = b.snapshot_at(t0 + Duration::from_secs(9));
        assert_eq!(s["transfers"][0]["bytes_per_second"], "0");
        assert_eq!(s["bytes_per_second"], "0");
        b.remove(7);
        assert!(b.is_empty());
        assert_eq!(b.snapshot()["transfers"].as_array().unwrap().len(), 0);
    }
}
