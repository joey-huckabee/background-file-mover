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
/// Child operations the last pass started (diagnostics and tests).
pub(crate) static LAST_PASS_OPS: AtomicU64 = AtomicU64::new(0);

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
    /// When the observation's reply arrived (conservative: never earlier).
    at: Instant,
}
/// Stable: the same identity as an earlier observation whose reply arrived at
/// least `settle` before this observation **started**.
pub(crate) fn settled(
    earlier: Option<(&ObjectIdentity, Instant)>,
    identity: &ObjectIdentity,
    started: Instant,
    settle: Duration,
) -> bool {
    earlier.is_some_and(|(seen, at)| {
        same_observation(seen, identity) && started.saturating_duration_since(at) >= settle
    })
}
struct JobState {
    /// Missing-review epoch when last seen: a reviewed reset makes the job
    /// due again at once.
    epoch: u32,
    due: Instant,
    backoff: Duration,
    cursor: usize,
    /// Custody validation of completed claims before new claims, resumable
    /// across passes (one child call each); `validated` once complete for the
    /// current pass over the files.
    validate_cursor: usize,
    validated: bool,
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
            crate::logging::diagnostic_line!(
                Warn,
                "wall_clock_jump",
                None,
                None,
                eprintln!("Wall clock jumped {jump:+} s; missing-file deadlines use wall time")
            );
            let expected = prev_wall + mono.saturating_duration_since(prev_mono).as_secs() as i64;
            let affected = if jump > 0 {
                store.missing_deadlines_between(expected, wall)
            } else {
                store.missing_recorded_after(wall)
            };
            match affected {
                Ok(ids) if !ids.is_empty() => crate::logging::diagnostic_line!(
                    Warn,
                    "clock_affected_windows",
                    None,
                    None,
                    eprintln!(
                        "Missing-file windows affected by the clock jump: jobs {ids:?} ({})",
                        if jump > 0 {
                            "deadline passed early"
                        } else {
                            "recorded after the new clock time; expiry is delayed"
                        }
                    )
                ),
                Ok(_) => (),
                Err(e) => crate::logging::diagnostic_line!(
                    Error,
                    "clock_lookup_failed",
                    None,
                    None,
                    eprintln!("Clock-jump lookup failed: {e}")
                ),
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
                crate::logging::diagnostic_line!(
                    Error,
                    "missing_retry_discovery_failed",
                    None,
                    None,
                    eprintln!("Missing-file retry discovery failed: {e}")
                );
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
        let before = claim_worker::CHILD_OPS.with(std::cell::Cell::get);
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
                validate_cursor: 0,
                validated: false,
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
        // The interference bound: a pass never starts more child operations
        // than its budget (claim-worker children; delivery is not involved).
        let used = claim_worker::CHILD_OPS.with(std::cell::Cell::get) - before;
        debug_assert!(
            used <= u64::from(BUDGET),
            "retry pass used {used} child operations"
        );
        LAST_PASS_OPS.store(used, Ordering::Relaxed);
    }
}

/// One job (design: Per file): the whole-job size policy first, then recovery
/// of authorized intents (not gated by deadline, block or a pending
/// cancellation), then the lifecycle gates, budgeted custody validation and
/// new claims from the job's cursor, all within the pass budget.
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
        crate::logging::diagnostic_line!(
            Warn,
            "missing_retry_failed",
            Some(id),
            None,
            eprintln!("Missing-file retry of job {id}: {what}: {e}")
        )
    };
    let back_off = |state: &mut JobState| {
        state.backoff = (state.backoff * 2).min(MAX);
        state.due = now + state.backoff;
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
    // The size policy holds before anything completes a handoff, recovery
    // included (same as a resend, which checks it before claiming).
    match crate::size_policy_ok(store, &status.job, check) {
        Ok(true) => (),
        Ok(false) => {
            back_off(state);
            return;
        }
        Err(e) => {
            log("size policy", &e);
            back_off(state);
            return;
        }
    }
    let mut progressed = false;
    // Recovery of authorized, unfinished intents.
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
    let Ok(Some(job)) = store.get(id) else {
        return;
    };
    if job.recording.handoff() == mover_core::Handoff::Ready202 {
        return;
    }
    // Lifecycle gates for new claims (no child operations): cancellation and
    // the deadline block, as a resend checks them.
    match (
        store.cancellation_requested(id),
        store.claim_blocked(id, crate::now()),
    ) {
        (Ok(false), Ok(false)) => (),
        _ => {
            back_off(state);
            return;
        }
    }
    // Custody of completed claims, as a resend validates it: one child call
    // per completed claim, budgeted and resumable.
    if !state.validated {
        while state.validate_cursor < files {
            if *budget == 0 || stop.load(Ordering::Relaxed) {
                state.due = now;
                return;
            }
            let index = state.validate_cursor;
            if let Ok(Some((_, true))) = store.claim_intent(id, index) {
                *budget -= 1;
                if let Err(e) = claim_worker::validate_one(store, guard, stop, id, index) {
                    log("custody", &crate::diagnostic::describe(&e));
                    state.validate_cursor = 0;
                    back_off(state);
                    return;
                }
            }
            state.validate_cursor += 1;
        }
        state.validated = true;
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
                let started = Instant::now();
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
                        let replied = Instant::now();
                        set_seen(id, index, Some(crate::now()));
                        let earlier = state.seen.get(&index).map(|s| (&s.identity, s.at));
                        if settled(earlier, &identity, started, settle) {
                            if *budget < CLAIM_COST {
                                state.cursor = index;
                                state.due = now;
                                return;
                            }
                            *budget -= CLAIM_COST;
                            let gate = RetryGate { stable: identity };
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
                                    state.seen.insert(
                                        index,
                                        Seen {
                                            identity,
                                            at: replied,
                                        },
                                    );
                                    replied
                                }
                            };
                            // Due just after the settle time has fully passed.
                            let w = at + settle + Duration::from_millis(50);
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
    // A full pass over the files ends this validation cycle.
    state.cursor = 0;
    state.validate_cursor = 0;
    state.validated = false;
    if progressed {
        state.backoff = FIRST;
        state.due = now + FIRST;
    } else if let Some(w) = wake {
        state.due = w;
    } else {
        back_off(state);
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
    fn settling_counts_from_the_reply_to_the_next_observation_start() {
        let id = |size| ObjectIdentity {
            device: 1,
            inode: 2,
            uid: 3,
            size,
            modified_seconds: 4,
            modified_nanos: 5,
            links: 1,
        };
        let settle = Duration::from_secs(5);
        let t0 = Instant::now();
        // The first reply arrived late (t0 + 4 s); an observation starting at
        // t0 + 6 s is only 2 s after it: not stable, however the visit began.
        let replied = t0 + Duration::from_secs(4);
        assert!(!settled(
            Some((&id(7), replied)),
            &id(7),
            t0 + Duration::from_secs(6),
            settle
        ));
        assert!(settled(
            Some((&id(7), replied)),
            &id(7),
            t0 + Duration::from_secs(9),
            settle
        ));
        // Changed or first observation: never stable.
        assert!(!settled(
            Some((&id(7), replied)),
            &id(8),
            t0 + Duration::from_secs(60),
            settle
        ));
        assert!(!settled(None, &id(7), t0 + Duration::from_secs(60), settle));
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
                validate_cursor: 0,
                validated: false,
                seen: HashMap::new(),
            },
        );
        assert!(r.wait(now) <= Duration::from_millis(500));
        r.touched(7);
        assert!(r.jobs[&7].due >= now + FIRST);
    }
}
