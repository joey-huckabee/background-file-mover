//! Guarded display-query pool. Commands and effect-gating reads never enter it.
use crate::{Config, control::Lifecycle};
use mover_store::{Store, read::{Budget, Context, Interrupt, Query, Reader, Snapshot}};
use std::{
    error::Error as StdError,
    sync::{Arc, Mutex, atomic::{AtomicBool, AtomicUsize, Ordering}, mpsc},
    thread::JoinHandle,
    time::{Duration, Instant},
};
use tokio::sync::oneshot;

const REQUEST: Duration = Duration::from_secs(2);
const ACTIVE: Duration = Duration::from_secs(1);
const POLL: Duration = Duration::from_millis(10);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Error { Busy, StorageUnavailable, GuardUnavailable, Stopping, InvalidQuery }

struct Ticket { until: Instant, cancelled: AtomicBool }
impl Ticket {
    fn cancelled(&self) -> bool {
        self.cancelled.load(Ordering::Acquire) || Instant::now() >= self.until
    }
}
struct Permit(Arc<AtomicUsize>);
impl Drop for Permit {
    fn drop(&mut self) { self.0.fetch_sub(1, Ordering::AcqRel); }
}
struct Work {
    query: Query,
    ticket: Arc<Ticket>,
    reply: oneshot::Sender<Result<Snapshot, Error>>,
    _permit: Permit,
    #[cfg(test)]
    pause: Option<TestPause>,
}
struct Active {
    generation: u64,
    budget: Arc<Budget>,
    ticket: Arc<Ticket>,
    interrupt: Arc<Interrupt>,
}
type Slot = Mutex<Option<Active>>;
struct Dispatch {
    senders: Mutex<Vec<mpsc::SyncSender<Work>>>,
    stopped: AtomicBool,
    used: Arc<AtomicUsize>,
    maximum: usize,
    next: AtomicUsize,
    lifecycle: Arc<Lifecycle>,
}

/// Clonable async-facing capability: only display queries, no Store/SQL access.
#[derive(Clone)]
pub struct Handle(Arc<Dispatch>);
pub struct Pending {
    result: oneshot::Receiver<Result<Snapshot, Error>>,
    ticket: Arc<Ticket>,
}
impl Pending {
    pub async fn reply(mut self) -> Result<Snapshot, Error> {
        let remaining = self.ticket.until.saturating_duration_since(Instant::now());
        if self.ticket.cancelled() { return Err(Error::StorageUnavailable); }
        let result = match tokio::time::timeout(remaining, &mut self.result).await {
            Ok(Ok(result)) => result,
            _ => Err(Error::StorageUnavailable),
        };
        if self.ticket.cancelled() { Err(Error::StorageUnavailable) } else { result }
    }
}
impl Drop for Pending {
    fn drop(&mut self) { self.ticket.cancelled.store(true, Ordering::Release); }
}
impl Handle {
    pub fn submit(&self, query: Query) -> Result<Pending, Error> {
        self.enqueue(query, #[cfg(test)] None)
    }
    fn enqueue(&self, query: Query, #[cfg(test)] pause: Option<TestPause>) -> Result<Pending, Error> {
        if self.0.stopped.load(Ordering::Acquire) || self.0.lifecycle.stop.load(Ordering::Acquire) { return Err(Error::Stopping); }
        self.0.used.fetch_update(Ordering::AcqRel, Ordering::Acquire, |n| {
            (n < self.0.maximum).then_some(n + 1)
        }).map_err(|_| Error::Busy)?;
        let permit = Permit(self.0.used.clone());
        let ticket = Arc::new(Ticket { until: Instant::now() + REQUEST, cancelled: AtomicBool::new(false) });
        let (reply, result) = oneshot::channel();
        let mut work = Work { query, ticket: ticket.clone(), reply, _permit: permit,
            #[cfg(test)] pause,
        };
        let senders = self.0.senders.try_lock().map_err(|_| Error::Busy)?;
        if self.0.stopped.load(Ordering::Acquire) || self.0.lifecycle.stop.load(Ordering::Acquire) { return Err(Error::Stopping); }
        if senders.is_empty() { return Err(Error::StorageUnavailable); }
        let first = self.0.next.fetch_add(1, Ordering::Relaxed) % senders.len();
        for offset in 0..senders.len() {
            match senders[(first + offset) % senders.len()].try_send(work) {
                Ok(()) => return Ok(Pending { result, ticket }),
                Err(mpsc::TrySendError::Full(returned)) => work = returned,
                Err(mpsc::TrySendError::Disconnected(_)) => return Err(Error::StorageUnavailable),
            }
        }
        Err(Error::Busy)
    }
}

pub struct ReadStore {
    pub handle: Handle,
    threads: Vec<JoinHandle<()>>,
    monitor: Option<JoinHandle<()>>,
    quit: Arc<AtomicBool>,
    readers_done: Arc<AtomicBool>,
    lifecycle: Arc<Lifecycle>,
    // Writer stays open until all reader connections and monitor actually exit.
    _writer: Arc<Store>,
    _guard: Arc<mover_fs::InstanceGuard>,
}
impl ReadStore {
    pub fn start(c: &Config, writer: Arc<Store>, guard: Arc<mover_fs::InstanceGuard>, lifecycle: Arc<Lifecycle>) -> Result<Self, Box<dyn StdError>> {
        Self::start_with(c, writer, guard, lifecycle, #[cfg(test)] None)
    }
    fn start_with(c: &Config, writer: Arc<Store>, guard: Arc<mover_fs::InstanceGuard>, lifecycle: Arc<Lifecycle>,
        #[cfg(test)] fail_reader: Option<usize>) -> Result<Self, Box<dyn StdError>> {
        if !(1..=8).contains(&c.database_readers) { return Err("invalid database reader count".into()); }
        let count = usize::from(c.database_readers);
        let dispatch = Arc::new(Dispatch {
            senders: Mutex::new(Vec::with_capacity(count)), stopped: AtomicBool::new(false),
            used: Arc::new(AtomicUsize::new(0)), maximum: 2 * count, next: AtomicUsize::new(0), lifecycle: lifecycle.clone(),
        });
        // Construct the owner before any fallible startup: Drop closes and joins
        // every partial start, without detaching or dropping the writer early.
        let mut pool = Self {
            handle: Handle(dispatch), threads: Vec::new(), monitor: None,
            quit: Arc::new(AtomicBool::new(false)), readers_done: Arc::new(AtomicBool::new(false)),
            lifecycle, _writer: writer, _guard: guard,
        };
        pool._guard.validate_reader_database(&c.state_database)
            .map_err(|_| "database reader state validation failed")?;
        let context = pool._writer.read_context().map_err(|_| "database reader validation context unavailable")?;
        if context.path() != std::path::Path::new(&c.state_database) {
            return Err("database reader writer path differs from guarded state".into());
        }
        let slots: Arc<Vec<Slot>> = Arc::new((0..count).map(|_| Mutex::new(None)).collect());
        let monitor_slots = slots.clone();
        let monitor_quit = pool.quit.clone();
        let monitor_done = pool.readers_done.clone();
        let monitor_lifecycle = pool.lifecycle.clone();
        let monitor_guard = pool._guard.clone();
        let (monitor_ready, monitor_started) = mpsc::sync_channel(1);
        pool.monitor = Some(std::thread::Builder::new().name("mover-read-monitor".into()).spawn(move || {
            let _guard = monitor_guard;
            let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            let _ = monitor_ready.send(());
            while !monitor_done.load(Ordering::Acquire) {
                for slot in monitor_slots.iter() {
                    // Hold the slot across interrupt: a worker cannot retire it
                    // and begin the next request while an old interrupt is pending.
                    let active = slot.lock().unwrap_or_else(|p| p.into_inner());
                    if let Some(active) = active.as_ref()
                        && (monitor_quit.load(Ordering::Acquire)
                            || monitor_lifecycle.stop.load(Ordering::Acquire)
                            || active.ticket.cancelled() || active.budget.expired())
                    {
                        active.budget.cancel();
                        active.interrupt.interrupt();
                    }
                }
                std::thread::sleep(POLL);
            }
            }));
            if outcome.is_err() {
                monitor_lifecycle.request_stop();
                monitor_quit.store(true, Ordering::Release);
            }
        }).map_err(|_| "database reader monitor unavailable")?);
        monitor_started.recv().map_err(|_| "database reader monitor failed to start")?;
        for index in 0..count {
            if pool.lifecycle.stop.load(Ordering::Acquire) { return Err("database reader startup stopping".into()); }
            let (sender, receiver) = mpsc::sync_channel(1);
            pool.handle.0.senders.lock().unwrap().push(sender);
            let (ready, result) = mpsc::sync_channel(1);
            let context = context.clone();
            let guard = pool._guard.clone();
            let lifecycle = pool.lifecycle.clone();
            let quit = pool.quit.clone();
            let slots = slots.clone();
            let path = c.state_database.clone();
            pool.threads.push(std::thread::Builder::new().name(format!("mover-read-{index}")).spawn(move || {
                let _guard = guard;
                let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                    #[cfg(test)]
                    if fail_reader == Some(index) {
                        let _ = ready.try_send(Err(()));
                        return;
                    }
                    let opened = open_reader(&_guard, &path, &context);
                    match opened {
                        Ok(mut reader) => {
                            if lifecycle.stop.load(Ordering::Acquire) || quit.load(Ordering::Acquire) {
                                let _ = ready.try_send(Err(()));
                                return;
                            }
                            if ready.try_send(Ok(())).is_err() { return; }
                            drive(&mut reader, receiver, &slots[index], &_guard, &lifecycle, &quit);
                        }
                        Err(()) => { let _ = ready.try_send(Err(())); }
                    }
                }));
                if outcome.is_err() {
                    lifecycle.request_stop();
                    quit.store(true, Ordering::Release);
                    let _ = ready.try_send(Err(()));
                }
            }).map_err(|_| format!("database reader {index} thread unavailable"))?);
            // No fixed startup scan deadline. Stop remains observable, while
            // Drop retains ownership through any genuinely blocked open.
            loop {
                match result.recv_timeout(POLL) {
                    Ok(Ok(())) => break,
                    Ok(Err(())) | Err(mpsc::RecvTimeoutError::Disconnected) => {
                        return Err(format!("database reader {index} open or validation failed").into());
                    }
                    Err(mpsc::RecvTimeoutError::Timeout) => {
                        if pool.lifecycle.stop.load(Ordering::Acquire) { return Err("database reader startup stopping".into()); }
                    }
                }
            }
        }
        if pool.lifecycle.stop.load(Ordering::Acquire) { return Err("database reader startup stopping".into()); }
        Ok(pool)
    }
}
fn open_reader(guard: &mover_fs::InstanceGuard, path: &str, context: &Context) -> Result<Reader, ()> {
    guard.validate_reader_database(path).map_err(|_| ())?;
    let reader = Reader::open(context).map_err(|_| ())?;
    guard.validate_reader_database(path).map_err(|_| ())?;
    Ok(reader)
}
fn drive(reader: &mut Reader, receiver: mpsc::Receiver<Work>, slot: &Slot,
    guard: &mover_fs::InstanceGuard, lifecycle: &Lifecycle, quit: &AtomicBool) {
    let interrupt = Arc::new(reader.interrupt_handle());
    let mut generation = 0_u64;
    while !quit.load(Ordering::Acquire) && !lifecycle.stop.load(Ordering::Acquire) {
        let work = match receiver.recv_timeout(POLL) {
            Ok(work) => work,
            Err(mpsc::RecvTimeoutError::Timeout) => continue,
            Err(mpsc::RecvTimeoutError::Disconnected) => break,
        };
        #[cfg(test)]
        let mut work = work;
        if work.ticket.cancelled() { continue; }
        if guard.validate().is_err() {
            let _ = work.reply.send(Err(Error::GuardUnavailable));
            continue;
        }
        let now = Instant::now();
        let until = (now + ACTIVE).min(work.ticket.until - Duration::from_millis(100));
        if now >= until || work.ticket.cancelled() { continue; }
        let budget = Arc::new(Budget::new(until));
        generation = generation.checked_add(1).expect("reader request generation exhausted");
        *slot.lock().unwrap_or_else(|p| p.into_inner()) = Some(Active {
            generation,
            budget: budget.clone(), ticket: work.ticket.clone(), interrupt: interrupt.clone(),
        });
        #[cfg(test)]
        if let Some(pause) = work.pause.take() { pause.wait(&budget); }
        // The monitor may cancel even between SQL statements. Reader checks the
        // same budget before BEGIN and before committing/returning a snapshot.
        let outcome = reader.query(work.query, &budget);
        let healthy = reader.healthy();
        // Retirement synchronizes with monitor interruption before next BEGIN.
        let retired = slot.lock().unwrap_or_else(|p| p.into_inner()).take();
        assert_eq!(retired.as_ref().map(|active| active.generation), Some(generation));
        if !healthy {
            lifecycle.request_stop();
            quit.store(true, Ordering::Release);
        }
        let result = if lifecycle.stop.load(Ordering::Acquire) || quit.load(Ordering::Acquire) {
            Err(Error::Stopping)
        } else if budget.expired() || work.ticket.cancelled() || !healthy {
            Err(Error::StorageUnavailable)
        } else {
            outcome.map_err(|error| match error {
                mover_store::StoreError::InvalidContext => Error::InvalidQuery,
                _ => Error::StorageUnavailable,
            })
        };
        let _ = work.reply.send(result);
    }
    while let Ok(work) = receiver.try_recv() {
        let _ = work.reply.send(Err(Error::Stopping));
    }
    // Dropping receiver discards queued work/permits; the connection closes on
    // its actual owner thread before this thread's guard reference is dropped.
}
impl Drop for ReadStore {
    fn drop(&mut self) {
        self.lifecycle.request_stop();
        self.handle.0.stopped.store(true, Ordering::Release);
        self.quit.store(true, Ordering::Release);
        self.handle.0.senders.lock().unwrap_or_else(|p| p.into_inner()).clear();
        for thread in self.threads.drain(..) { let _ = thread.join(); }
        self.readers_done.store(true, Ordering::Release);
        if let Some(monitor) = self.monitor.take() { let _ = monitor.join(); }
    }
}

#[cfg(test)]
struct TestPause { entered: mpsc::SyncSender<()>, release: mpsc::Receiver<()>, panic: bool }
#[cfg(test)]
impl TestPause {
    fn wait(self, budget: &Budget) {
        let _ = self.entered.send(());
        assert!(!self.panic, "test-only reader panic");
        while !budget.expired() {
            match self.release.recv_timeout(POLL) {
                Ok(()) | Err(mpsc::RecvTimeoutError::Disconnected) => break,
                Err(mpsc::RecvTimeoutError::Timeout) => (),
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{fs, os::unix::fs::{PermissionsExt, symlink}, path::PathBuf, sync::atomic::AtomicU64};
    static NEXT: AtomicU64 = AtomicU64::new(0);
    struct Fixture {
        root: PathBuf,
        writer: Option<Arc<Store>>,
        guard: Option<Arc<mover_fs::InstanceGuard>>,
        config: Config,
    }
    impl Fixture {
        fn new(count: u8) -> Self {
            let root = std::env::temp_dir().join(format!("mover-read-test-{}-{}", std::process::id(), NEXT.fetch_add(1, Ordering::Relaxed)));
            fs::create_dir(&root).unwrap();
            fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
            let mut config: Config = serde_json::from_str(include_str!("../../../config/local.example.json")).unwrap();
            config.database_readers = count;
            config.state_database = root.join("state.sqlite").to_str().unwrap().to_owned();
            let guard = Arc::new(mover_fs::InstanceGuard::for_database(&config.state_database).unwrap());
            guard.prepare_database(&config.state_database).unwrap();
            let writer = Arc::new(Store::open(&config.state_database).unwrap());
            writer.configure_limits(64, 1024 * 1024).unwrap();
            Self { root, writer: Some(writer), guard: Some(guard), config }
        }
        fn writer(&self) -> Arc<Store> { self.writer.as_ref().unwrap().clone() }
        fn guard(&self) -> Arc<mover_fs::InstanceGuard> { self.guard.as_ref().unwrap().clone() }
        fn pool(&self) -> ReadStore {
            ReadStore::start(&self.config, self.writer(), self.guard(), Lifecycle::new(Arc::new(AtomicBool::new(false)), 5)).unwrap()
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            self.writer.take();
            self.guard.take();
            fs::remove_dir_all(&self.root).unwrap();
        }
    }
    fn block_on<T>(future: impl std::future::Future<Output=T>) -> T {
        tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap().block_on(future)
    }
    fn paused(handle: &Handle) -> (Pending, mpsc::Receiver<()>, mpsc::SyncSender<()>) {
        let (entered, reached) = mpsc::sync_channel(1);
        let (release, wait) = mpsc::sync_channel(1);
        let pending = handle.enqueue(Query::Status(1), Some(TestPause { entered, release: wait, panic: false })).unwrap();
        (pending, reached, release)
    }
    #[test]
    fn database_readers_default_and_validation() {
        let original: serde_json::Value = serde_json::from_str(include_str!("../../../config/local.example.json")).unwrap();
        let default: Config = serde_json::from_value(original.clone()).unwrap();
        assert_eq!(default.database_readers, 2);
        for value in [serde_json::json!(0), serde_json::json!(1), serde_json::json!(8), serde_json::json!(9)] {
            let mut config = original.clone();
            config["database_readers"] = value.clone();
            let config: Config = serde_json::from_value(config).unwrap();
            assert_eq!(config.validate().is_ok(), value == 1 || value == 8);
        }
        for value in [serde_json::json!(-1), serde_json::json!(1.5), serde_json::json!("2"), serde_json::Value::Null] {
            let mut config = original.clone();
            config["database_readers"] = value;
            assert!(serde_json::from_value::<Config>(config).is_err());
        }
    }
    #[test]
    fn configured_reader_counts_open_and_join_actual_owner_threads() {
        for count in [1, 2, 8] {
            let f = Fixture::new(count);
            let pool = f.pool();
            assert_eq!(pool.threads.len(), usize::from(count));
            assert!(matches!(block_on(pool.handle.submit(Query::Retention(None)).unwrap().reply()), Ok(Snapshot::Retention(Some(_)))));
            drop(pool);
            assert_eq!(Arc::strong_count(f.guard.as_ref().unwrap()), 1);
            assert_eq!(Arc::strong_count(f.writer.as_ref().unwrap()), 1);
        }
    }
    #[test]
    fn bounded_pool_drops_cancelled_queued_work_and_returns_permits() {
        let f = Fixture::new(1);
        let pool = f.pool();
        let (running, reached, release) = paused(&pool.handle);
        reached.recv_timeout(Duration::from_secs(2)).unwrap();
        let queued = pool.handle.submit(Query::Status(1)).unwrap();
        assert!(matches!(pool.handle.submit(Query::Status(1)), Err(Error::Busy)));
        drop(queued);
        release.send(()).unwrap();
        assert!(matches!(block_on(running.reply()), Ok(Snapshot::Status(None))));
        let until = Instant::now() + Duration::from_secs(2);
        while pool.handle.0.used.load(Ordering::Acquire) != 0 {
            assert!(Instant::now() < until);
            std::thread::yield_now();
        }
        assert!(matches!(block_on(pool.handle.submit(Query::Retention(None)).unwrap().reply()), Ok(Snapshot::Retention(Some(_)))));
    }
    #[test]
    fn full_first_queue_tries_the_other_reader() {
        let f = Fixture::new(2);
        let pool = f.pool();
        let (first, first_ready, first_release) = paused(&pool.handle);
        first_ready.recv_timeout(Duration::from_secs(2)).unwrap();
        let (second, second_ready, second_release) = paused(&pool.handle);
        second_ready.recv_timeout(Duration::from_secs(2)).unwrap();
        let queued_first = pool.handle.submit(Query::Status(1)).unwrap();
        pool.handle.0.next.store(0, Ordering::Relaxed);
        let queued_other = pool.handle.submit(Query::Status(1)).expect("other queue remains available");
        assert!(matches!(pool.handle.submit(Query::Status(1)), Err(Error::Busy)));
        first_release.send(()).unwrap();
        second_release.send(()).unwrap();
        for pending in [first, second, queued_first, queued_other] {
            assert!(matches!(block_on(pending.reply()), Ok(Snapshot::Status(None))));
        }
    }
    #[test]
    fn reader_panic_requests_stop_and_drop_joins_its_guard_owners() {
        let f = Fixture::new(1);
        let pool = f.pool();
        let (entered, reached) = mpsc::sync_channel(1);
        let (_release, wait) = mpsc::sync_channel(1);
        let pending = pool.handle.enqueue(Query::Status(1), Some(TestPause { entered, release: wait, panic: true })).unwrap();
        reached.recv_timeout(Duration::from_secs(2)).unwrap();
        assert!(matches!(block_on(pending.reply()), Err(Error::StorageUnavailable)));
        let until = Instant::now() + Duration::from_secs(2);
        while !pool.lifecycle.stop.load(Ordering::Acquire) {
            assert!(Instant::now() < until);
            std::thread::yield_now();
        }
        drop(pool);
        assert_eq!(Arc::strong_count(f.guard.as_ref().unwrap()), 1);
    }
    #[test]
    fn guard_checked_again_for_work_queued_before_name_substitution() {
        let f = Fixture::new(1);
        let pool = f.pool();
        let (running, reached, release) = paused(&pool.handle);
        reached.recv_timeout(Duration::from_secs(2)).unwrap();
        let queued = pool.handle.submit(Query::Status(1)).unwrap();
        fs::rename(f.root.join("instance.lock"), f.root.join("original.lock")).unwrap();
        release.send(()).unwrap();
        let _ = block_on(running.reply());
        assert!(matches!(block_on(queued.reply()), Err(Error::GuardUnavailable)));
        for query in [Query::Page { cursor: 0, limit: 1, descending: false },
            Query::Search { needle: "data".into(), before: i64::MAX, until: 0 }, Query::Retention(None)] {
            assert!(matches!(block_on(pool.handle.submit(query).unwrap().reply()), Err(Error::GuardUnavailable)));
        }
    }
    #[test]
    fn active_deadline_interrupt_does_not_poison_the_next_request() {
        let f = Fixture::new(1);
        let pool = f.pool();
        let (running, reached, _release) = paused(&pool.handle);
        reached.recv_timeout(Duration::from_secs(2)).unwrap();
        assert!(matches!(block_on(running.reply()), Err(Error::StorageUnavailable)));
        assert!(matches!(block_on(pool.handle.submit(Query::Status(1)).unwrap().reply()), Ok(Snapshot::Status(None))));
    }
    #[test]
    fn shutdown_joins_readers_releases_guard_and_closes_surviving_handles() {
        let f = Fixture::new(2);
        let pool = f.pool();
        let handle = pool.handle.clone();
        let (running, reached, _release) = paused(&handle);
        reached.recv_timeout(Duration::from_secs(2)).unwrap();
        let guard = f.guard();
        drop(pool);
        assert_eq!(Arc::strong_count(&guard), 2); // fixture plus this test, no thread.
        assert!(matches!(handle.submit(Query::Status(1)), Err(Error::Stopping)));
        assert!(matches!(block_on(running.reply()), Err(Error::Stopping)));
        assert!(mover_fs::InstanceGuard::for_database(&f.config.state_database).is_err());
    }
    #[test]
    fn partial_startup_failure_joins_already_started_reader_and_monitor() {
        let f = Fixture::new(2);
        let lifecycle = Lifecycle::new(Arc::new(AtomicBool::new(false)), 5);
        let guard = f.guard();
        let result = ReadStore::start_with(&f.config, f.writer(), guard.clone(), lifecycle.clone(), Some(1));
        assert!(result.is_err());
        assert!(lifecycle.stop.load(Ordering::Acquire));
        assert_eq!(Arc::strong_count(&guard), 2);
        assert_eq!(Arc::strong_count(f.writer.as_ref().unwrap()), 1);
    }
    #[test]
    fn unsafe_sidecar_refuses_startup_without_fallback_or_mutation() {
        let f = Fixture::new(2);
        let sidecar = f.root.join("state.sqlite-journal");
        symlink("foreign", &sidecar).unwrap();
        let result = ReadStore::start(&f.config, f.writer(), f.guard(), Lifecycle::new(Arc::new(AtomicBool::new(false)), 5));
        assert!(result.is_err());
        assert_eq!(fs::read_link(sidecar).unwrap(), PathBuf::from("foreign"));
    }
}
