//! Timer-driven missing-file retries (docs/MISSING-FILE-RETRY-DESIGN.md). Runs
//! on the `mover-local-claim` thread between producer requests, so retries are
//! serialized with producer claims. In-memory state only: observations,
//! cursors and schedules (a restart starts fresh settle periods).
use crate::claim_worker::{self, RetryGate, same_observation};
use mover_core::ObjectIdentity;
use mover_fs::LocalClaimLock;
use mover_store::Store;
use std::collections::HashMap;
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::time::{Duration, Instant};

/// Child operations per pass. An Observe and a recovery or claim step count;
/// a claim counts as three (Observe, Allocate, Apply).
pub(crate) const BUDGET: u32 = 16;
const CLAIM_COST: u32 = 3;
const FIRST: Duration = Duration::from_secs(2);
const MAX: Duration = Duration::from_secs(30);
/// How often the store is asked for jobs to visit when nothing else is due.
const DISCOVERY: Duration = Duration::from_secs(2);

/// Status: (job, file) -> (wall time last seen present, settling).
pub(crate) static PROBES: Mutex<Option<HashMap<(i64, usize), i64>>> = Mutex::new(None);
/// Wall-clock jumps seen since start (Settings).
pub(crate) static CLOCK_JUMPS: AtomicU64 = AtomicU64::new(0);

/// Wall time last seen for a probed file (None when absent or not probed).
pub(crate) fn last_seen(job: i64, file: usize) -> Option<i64> {
    PROBES
        .lock()
        .ok()
        .and_then(|p| p.as_ref().and_then(|m| m.get(&(job, file)).copied()))
}
fn set_seen(job: i64, file: usize, wall: Option<i64>) {
    if let Ok(mut p) = PROBES.lock() {
        let map = p.get_or_insert_with(HashMap::new);
        match wall {
            Some(w) => {
                map.insert((job, file), w);
            }
            None => {
                map.remove(&(job, file));
            }
        }
    }
}
fn forget_job(job: i64) {
    if let Ok(mut p) = PROBES.lock()
        && let Some(map) = p.as_mut()
    {
        map.retain(|(j, _), _| *j != job);
    }
}

/// Seconds the wall clock moved beyond elapsed monotonic time, when more than
/// 2 s either way (a clock jump); None otherwise.
pub(crate) fn clock_jump(
    prev_wall: i64,
    prev_mono: Instant,
    wall: i64,
    mono: Instant,
) -> Option<i64> {
    let mono_s = mono.saturating_duration_since(prev_mono).as_secs_f64();
    let drift = (wall - prev_wall) as f64 - mono_s;
    (drift.abs() > 2.0).then_some(drift.round() as i64)
}

struct Seen {
    identity: ObjectIdentity,
    at: Instant,
}
struct JobState {
    /// Missing-review epoch when last seen: a reviewed reset makes the job
    /// due again at once.
    epoch: u32,
    due: Instant,
    backoff: Duration,
    cursor: usize,
    seen: HashMap<usize, Seen>,
}

pub(crate) struct Retry {
    settle: Duration,
    jobs: HashMap<i64, JobState>,
    last_job: i64,
    discovered: Option<Instant>,
    clock: Option<(i64, Instant)>,
}

impl Retry {
    pub(crate) fn new(settle: Duration) -> Self {
        Self {
            settle,
            jobs: HashMap::new(),
            last_job: 0,
            discovered: None,
            clock: None,
        }
    }
    /// How long the claim thread may wait for a request before a pass is due.
    pub(crate) fn wait(&self, now: Instant) -> Duration {
        let discovery = self.discovered.map_or(now, |d| d + DISCOVERY);
        let next = self
            .jobs
            .values()
            .map(|j| j.due)
            .chain([discovery])
            .min()
            .unwrap_or(discovery);
        next.saturating_duration_since(now)
            .max(Duration::from_millis(10))
    }
    pub(crate) fn due(&self, now: Instant) -> bool {
        self.discovered.is_none_or(|d| now >= d + DISCOVERY)
            || self.jobs.values().any(|j| j.due <= now)
    }
    /// A producer request for this job: restart its backoff.
    pub(crate) fn touched(&mut self, job: i64) {
        if let Some(j) = self.jobs.get_mut(&job) {
            j.backoff = FIRST;
            j.due = Instant::now() + FIRST;
        }
    }

    fn check_clock(&mut self, store: &Store, wall: i64, mono: Instant) {
        if let Some((prev_wall, prev_mono)) = self.clock
            && let Some(jump) = clock_jump(prev_wall, prev_mono, wall, mono)
        {
            CLOCK_JUMPS.fetch_add(1, Ordering::Relaxed);
            eprintln!("Wall clock jumped {jump:+} s; missing-file deadlines use wall time");
            let expected = prev_wall + mono.saturating_duration_since(prev_mono).as_secs() as i64;
            let affected = if jump > 0 {
                store.missing_deadlines_between(expected, wall)
            } else {
                store.missing_recorded_after(wall)
            };
            match affected {
                Ok(ids) if !ids.is_empty() => eprintln!(
                    "Missing-file windows affected by the clock jump: jobs {ids:?} ({})",
                    if jump > 0 {
                        "deadline passed early"
                    } else {
                        "recorded after the new clock time; expiry is delayed"
                    }
                ),
                Ok(_) => (),
                Err(e) => eprintln!("Clock-jump lookup failed: {e}"),
            }
        }
        self.clock = Some((wall, mono));
    }

    /// One budgeted pass (design: Scheduling). The caller sets `claim_active`.
    pub(crate) fn pass(
        &mut self,
        store: &Store,
        guard: &LocalClaimLock,
        stop: &AtomicBool,
        check_expected_sizes: bool,
    ) {
        let now = Instant::now();
        let wall = crate::now();
        self.check_clock(store, wall, now);
        self.discovered = Some(now);
        let found = match store.missing_retry_jobs() {
            Ok(found) => found,
            Err(e) => {
                eprintln!("Missing-file retry discovery failed: {e}");
                return;
            }
        };
        let ids: Vec<i64> = found.iter().map(|(id, _)| *id).collect();
        for &(id, epoch) in &found {
            if let Some(j) = self.jobs.get_mut(&id)
                && j.epoch != epoch
            {
                j.epoch = epoch;
                j.backoff = FIRST;
                j.due = now;
            }
        }
        for gone in self
            .jobs
            .keys()
            .filter(|id| !ids.contains(id))
            .copied()
            .collect::<Vec<_>>()
        {
            self.jobs.remove(&gone);
            forget_job(gone);
        }
        // Round-robin from the job after the last one visited.
        let start = ids.iter().position(|&id| id > self.last_job).unwrap_or(0);
        let order: Vec<i64> = ids[start..].iter().chain(&ids[..start]).copied().collect();
        let mut budget = BUDGET;
        for id in order {
            if budget == 0 || stop.load(Ordering::Relaxed) {
                break;
            }
            let epoch = found.iter().find(|(j, _)| *j == id).map_or(0, |(_, e)| *e);
            let state = self.jobs.entry(id).or_insert_with(|| JobState {
                epoch,
                due: now,
                backoff: FIRST,
                cursor: 0,
                seen: HashMap::new(),
            });
            if state.due > now {
                continue;
            }
            self.last_job = id;
            let settle = self.settle;
            visit(
                store,
                guard,
                stop,
                check_expected_sizes,
                id,
                state,
                settle,
                &mut budget,
            );
        }
    }
}

/// One job: recovery of authorized intents first (not gated), then new claims
/// behind the shared gates, from the job's cursor, within the budget.
#[allow(clippy::too_many_arguments)]
fn visit(
    store: &Store,
    guard: &LocalClaimLock,
    stop: &AtomicBool,
    check: bool,
    id: i64,
    state: &mut JobState,
    settle: Duration,
    budget: &mut u32,
) {
    let now = Instant::now();
    let log = |what: &str, e: &dyn std::fmt::Display| {
        eprintln!("Missing-file retry of job {id}: {what}: {e}")
    };
    let Ok(Some(status)) = store.status(id) else {
        return;
    };
    let files = status.job.recording.submission().files().len();
    // A settled cancellation promises no further work.
    if status
        .cancellation
        .as_ref()
        .is_some_and(|c| c.state == mover_store::CancelState::Cancelled)
    {
        state.due = now + MAX;
        return;
    }
    let mut progressed = false;
    // Recovery of authorized, unfinished intents: not gated by deadline,
    // block or a pending cancellation request.
    for index in 0..files {
        if let Ok(Some((_, false))) = store.claim_intent(id, index) {
            if *budget < CLAIM_COST {
                state.due = now; // Continue on the next pass.
                return;
            }
            *budget -= CLAIM_COST;
            match claim_worker::claim(store, guard, stop, id, index, check) {
                Ok(_) => progressed = true,
                Err(e) => log("recovery", &crate::diagnostic::describe(&e)),
            }
        }
    }
    // New claims: the same whole-job gates as a producer request.
    let Ok(Some(job)) = store.get(id) else {
        return;
    };
    if job.recording.handoff() == mover_core::Handoff::Ready202 {
        return;
    }
    if *budget == 0 {
        state.due = now;
        return;
    }
    *budget -= 1; // Gates include custody validation of completed claims.
    if crate::claim_gates(store, guard, stop, &job, check).is_err() {
        // Blocked, cancellation requested, custody or size policy: no new
        // claims; a block or reset is visible to the next discovery.
        state.backoff = MAX;
        state.due = now + MAX;
        return;
    }
    let mut wake: Option<Instant> = None;
    let mut index = state.cursor.min(files);
    while index < files {
        if *budget == 0 || stop.load(Ordering::Relaxed) {
            state.cursor = index;
            state.due = now;
            return;
        }
        match store.claim_intent(id, index) {
            // Completed: the claim's recorded-size check (no child operation).
            Ok(Some((_, true))) => {
                if let Err(e) = claim_worker::claim(store, guard, stop, id, index, check) {
                    log("completed claim", &crate::diagnostic::describe(&e));
                    break;
                }
            }
            Ok(Some((_, false))) => (), // Recovery above.
            Ok(None) => {
                *budget -= 1;
                match claim_worker::observe(store, guard, stop, id, index, check) {
                    Ok(None) => {
                        // Absent: record its first absence once (deadline starts).
                        if let Err(e) = store.note_missing(id, index, crate::now()) {
                            log("first absence", &e);
                        }
                        state.seen.remove(&index);
                        set_seen(id, index, None);
                    }
                    Ok(Some(identity)) => {
                        set_seen(id, index, Some(crate::now()));
                        let stable = state.seen.get(&index).is_some_and(|s| {
                            same_observation(&s.identity, &identity)
                                && now.saturating_duration_since(s.at) >= settle
                        });
                        if stable {
                            if *budget < CLAIM_COST {
                                state.cursor = index;
                                state.due = now;
                                return;
                            }
                            *budget -= CLAIM_COST;
                            let gate = RetryGate {
                                stable: identity,
                                now: crate::now(),
                            };
                            match claim_worker::claim_stable(
                                store, guard, stop, id, index, check, &gate,
                            ) {
                                Ok(Some(_)) => progressed = true,
                                Ok(None) => (), // Changed or not admitted: nothing recorded.
                                Err(e) => log("claim", &crate::diagnostic::describe(&e)),
                            }
                            state.seen.remove(&index);
                            set_seen(id, index, None);
                        } else {
                            let at = match state.seen.get(&index) {
                                Some(s) if same_observation(&s.identity, &identity) => s.at,
                                _ => {
                                    state.seen.insert(index, Seen { identity, at: now });
                                    now
                                }
                            };
                            let w = at + settle;
                            wake = Some(wake.map_or(w, |x| x.min(w)));
                        }
                    }
                    Err(e) => {
                        log("observe", &crate::diagnostic::describe(&e));
                        break;
                    }
                }
            }
            Err(e) => {
                log("store", &e);
                break;
            }
        }
        index += 1;
    }
    state.cursor = 0;
    if progressed {
        state.backoff = FIRST;
        state.due = now + FIRST;
    } else if let Some(w) = wake {
        state.due = w;
    } else {
        state.backoff = (state.backoff * 2).min(MAX);
        state.due = now + state.backoff;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn clock_jumps_are_wall_moves_beyond_monotonic_time() {
        let t0 = Instant::now();
        let t10 = t0 + Duration::from_secs(10);
        assert_eq!(clock_jump(1000, t0, 1010, t10), None);
        assert_eq!(clock_jump(1000, t0, 1012, t10), None, "within 2 s");
        assert_eq!(clock_jump(1000, t0, 1070, t10), Some(60));
        assert_eq!(clock_jump(1000, t0, 950, t10), Some(-60));
        assert_eq!(clock_jump(1000, t0, 1000, t10), Some(-10));
    }
    #[test]
    fn scheduling_waits_until_the_earliest_due_job_or_discovery() {
        let mut r = Retry::new(Duration::from_secs(5));
        let now = Instant::now();
        assert!(r.due(now), "first discovery is due at once");
        r.discovered = Some(now);
        assert!(!r.due(now));
        assert!(r.wait(now) <= DISCOVERY);
        r.jobs.insert(
            7,
            JobState {
                epoch: 0,
                due: now + Duration::from_millis(500),
                backoff: FIRST,
                cursor: 0,
                seen: HashMap::new(),
            },
        );
        assert!(r.wait(now) <= Duration::from_millis(500));
        r.touched(7);
        assert!(r.jobs[&7].due >= now + FIRST);
    }
}
