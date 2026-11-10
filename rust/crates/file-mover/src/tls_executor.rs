//! Bounded native TLS execution on two owned current-thread reactors.
//! No job is polled on the caller's executor. Async cancellation cannot preempt
//! non-yielding work: shutdown retains ownership and joins its actual OS thread.
use crate::control::Lifecycle;
use std::{
    error::Error,
    future::{Future, poll_fn},
    pin::Pin,
    sync::{
        Arc,
        atomic::{AtomicBool, AtomicUsize, Ordering},
        mpsc,
    },
    task::{Context, Poll},
    thread::JoinHandle,
    time::{Duration, Instant},
};
use tokio::{
    sync::{OwnedSemaphorePermit, Semaphore, mpsc as queue},
    task::{JoinError, JoinSet},
};

type Result<T> = std::result::Result<T, Box<dyn Error>>;
pub(crate) type Job = Pin<Box<dyn Future<Output = ()> + Send + 'static>>;
const THREADS: usize = 2;
const QUEUE: usize = 3;
const JOBS: usize = 6;
const STOP_POLL: Duration = Duration::from_millis(100);
const START_WAIT: Duration = Duration::from_secs(5);

// Struct fields drop in declaration order: the future (including a synchronous
// destructor) exits before its owned admission permit can be returned.
struct Admitted {
    job: Job,
    _permit: OwnedSemaphorePermit,
}
impl Future for Admitted {
    type Output = ();
    fn poll(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<()> {
        self.get_mut().job.as_mut().poll(cx)
    }
}

pub(crate) struct Pool {
    senders: Vec<queue::Sender<Admitted>>,
    threads: Vec<JoinHandle<()>>,
    slots: Arc<Semaphore>,
    next: AtomicUsize,
    quit: Arc<AtomicBool>,
    lifecycle: Arc<Lifecycle>,
    // Retain a caller-side guard until both actual thread handles are joined.
    _guard: Arc<mover_fs::InstanceGuard>,
}
impl Pool {
    pub(crate) fn start(
        guard: Arc<mover_fs::InstanceGuard>,
        lifecycle: Arc<Lifecycle>,
    ) -> Result<Self> {
        // Construct the owner first: every later error runs the same close/join
        // path, including partial thread startup and runtime readiness failure.
        let mut pool = Self {
            senders: Vec::with_capacity(THREADS),
            threads: Vec::with_capacity(THREADS),
            slots: Arc::new(Semaphore::new(JOBS)),
            next: AtomicUsize::new(0),
            quit: Arc::new(AtomicBool::new(false)),
            lifecycle,
            _guard: guard,
        };
        pool._guard.validate().map_err(|_| "TLS executor instance unavailable")?;
        if pool.lifecycle.stop.load(Ordering::Acquire) {
            return Err("TLS executor service stopping".into());
        }
        let (ready_sender, ready) = mpsc::sync_channel(THREADS);
        for index in 0..THREADS {
            let (sender, receiver) = queue::channel(QUEUE);
            pool.senders.push(sender);
            let guard = pool._guard.clone();
            let quit = pool.quit.clone();
            let lifecycle = pool.lifecycle.clone();
            let ready_sender = ready_sender.clone();
            let thread = std::thread::Builder::new()
                .name(format!("mover-tls-executor-{index}"))
                .spawn(move || {
                    // This guard outlives runtime shutdown and all job drops.
                    let _guard = guard;
                    let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                        let runtime = match tokio::runtime::Builder::new_current_thread()
                            .enable_all()
                            .build()
                        {
                            Ok(runtime) => runtime,
                            Err(_) => {
                                fail_closed(&quit, &lifecycle);
                                let _ = ready_sender.try_send(Err("TLS executor runtime unavailable"));
                                return;
                            }
                        };
                        if ready_sender.try_send(Ok(index)).is_err() {
                            fail_closed(&quit, &lifecycle);
                            return;
                        }
                        runtime.block_on(drive(receiver, &quit, &lifecycle));
                        if !stopping(&quit, &lifecycle) {
                            fail_closed(&quit, &lifecycle);
                        }
                    }));
                    if outcome.is_err() {
                        fail_closed(&quit, &lifecycle);
                        // Never block on a startup channel after start returned.
                        let _ = ready_sender.try_send(Err("TLS executor thread failed"));
                    }
                })
                .map_err(|_| "TLS executor thread unavailable")?;
            pool.threads.push(thread);
        }
        drop(ready_sender);
        let deadline = Instant::now() + START_WAIT;
        let mut received = [false; THREADS];
        for _ in 0..THREADS {
            let index = ready
                .recv_timeout(deadline.saturating_duration_since(Instant::now()))
                .map_err(|_| "TLS executor startup unavailable or timed out")?
                .map_err(|_| "TLS executor runtime readiness failed")?;
            if index >= THREADS || received[index] {
                return Err("TLS executor invalid readiness".into());
            }
            received[index] = true;
        }
        if stopping(&pool.quit, &pool.lifecycle) {
            return Err("TLS executor stopped during startup".into());
        }
        Ok(pool)
    }

    /// True means queued, never authenticated/admitted by the transfer worker.
    /// On false, ownership of the supplied future is dropped here. Each job must
    /// own/join any nested work: detached child tasks cannot share this budget.
    pub(crate) fn try_spawn(&self, job: Job) -> bool {
        if stopping(&self.quit, &self.lifecycle) {
            return false;
        }
        let Ok(permit) = self.slots.clone().try_acquire_owned() else {
            return false;
        };
        let mut admitted = Admitted { job, _permit: permit };
        if stopping(&self.quit, &self.lifecycle) {
            return false;
        }
        let first = self.next.fetch_add(1, Ordering::Relaxed) % THREADS;
        for offset in 0..THREADS {
            match self.senders[(first + offset) % THREADS].try_send(admitted) {
                Ok(()) => return true,
                Err(queue::error::TrySendError::Full(job)) => admitted = job,
                Err(queue::error::TrySendError::Closed(_)) => {
                    // A missing worker is not permission to silently run at
                    // reduced protection, even when the other queue has room.
                    fail_closed(&self.quit, &self.lifecycle);
                    return false;
                }
            }
        }
        false
    }
}
impl Drop for Pool {
    fn drop(&mut self) {
        // Share the manager's activation/admission boundary before any queue or
        // future is discarded. request_stop preserves the original deadline.
        self.lifecycle.request_stop();
        self.quit.store(true, Ordering::Release);
        self.slots.close();
        self.senders.clear();
        for thread in self.threads.drain(..) {
            if thread.join().is_err() {
                fail_closed(&self.quit, &self.lifecycle);
            }
        }
    }
}

fn stopping(quit: &AtomicBool, lifecycle: &Lifecycle) -> bool {
    quit.load(Ordering::Acquire) || lifecycle.stop.load(Ordering::Acquire)
}
fn fail_closed(quit: &AtomicBool, lifecycle: &Lifecycle) {
    lifecycle.request_stop();
    quit.store(true, Ordering::Release);
}
fn completion(result: std::result::Result<(), JoinError>, quit: &AtomicBool, lifecycle: &Lifecycle) {
    if result.is_err_and(|error| error.is_panic()) {
        fail_closed(quit, lifecycle);
    }
}

enum Event {
    Stop,
    Tick,
    Completion(std::result::Result<(), JoinError>),
    Job(Admitted),
}
async fn drive(mut receiver: queue::Receiver<Admitted>, quit: &AtomicBool, lifecycle: &Lifecycle) {
    let mut tasks = JoinSet::new();
    let mut tick = tokio::time::interval(STOP_POLL);
    tick.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    loop {
        // Harvest before every dispatch, including immediately completed jobs.
        while let Some(result) = tasks.try_join_next() {
            completion(result, quit, lifecycle);
        }
        let event = poll_fn(|cx| {
            if stopping(quit, lifecycle) {
                return Poll::Ready(Event::Stop);
            }
            // Prefer completions over incoming work. A separate JoinSet length
            // cap also bounds completed records independently of permit return.
            if let Poll::Ready(Some(result)) = tasks.poll_join_next(cx) {
                return Poll::Ready(Event::Completion(result));
            }
            if tick.poll_tick(cx).is_ready() {
                return Poll::Ready(Event::Tick);
            }
            if tasks.len() < JOBS {
                match receiver.poll_recv(cx) {
                    Poll::Ready(Some(job)) => return Poll::Ready(Event::Job(job)),
                    Poll::Ready(None) => return Poll::Ready(Event::Stop),
                    Poll::Pending => (),
                }
            }
            Poll::Pending
        })
        .await;
        match event {
            Event::Stop => break,
            Event::Tick => (),
            Event::Completion(result) => completion(result, quit, lifecycle),
            Event::Job(job) => {
                if stopping(quit, lifecycle) {
                    drop(job);
                    break;
                }
                tasks.spawn(job);
            }
        }
    }
    lifecycle.request_stop();
    receiver.close();
    while let Ok(job) = receiver.try_recv() {
        drop(job);
    }
    tasks.abort_all();
    while let Some(result) = tasks.join_next().await {
        completion(result, quit, lifecycle);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{os::unix::fs::PermissionsExt, path::PathBuf};
    static NEXT: AtomicUsize = AtomicUsize::new(0);

    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "tls-executor-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            std::fs::create_dir(&path).unwrap();
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o700)).unwrap();
            Self(path)
        }
        fn guard(&self) -> Arc<mover_fs::InstanceGuard> {
            Arc::new(mover_fs::InstanceGuard::for_database(
                self.0.join("jobs.sqlite").to_str().unwrap(),
            ).unwrap())
        }
        fn pool(&self) -> (Pool, Arc<Lifecycle>) {
            let lifecycle = Lifecycle::new(Arc::new(AtomicBool::new(false)), 5);
            (Pool::start(self.guard(), lifecycle.clone()).unwrap(), lifecycle)
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            std::fs::remove_dir_all(&self.0).unwrap();
        }
    }
    fn until(mut condition: impl FnMut() -> bool) {
        let deadline = Instant::now() + Duration::from_secs(5);
        while !condition() {
            assert!(Instant::now() < deadline, "TLS executor test deadline");
            std::thread::sleep(Duration::from_millis(1));
        }
    }
    struct CountDrop(Arc<AtomicUsize>);
    impl Drop for CountDrop {
        fn drop(&mut self) {
            self.0.fetch_add(1, Ordering::AcqRel);
        }
    }

    #[test]
    fn six_jobs_bound_queued_and_running_and_stop_drops_every_future() {
        let fixture = Fixture::new();
        let (pool, stop) = fixture.pool();
        let started = Arc::new(AtomicUsize::new(0));
        let dropped = Arc::new(AtomicUsize::new(0));
        for _ in 0..JOBS {
            let started = started.clone();
            let held = CountDrop(dropped.clone());
            assert!(pool.try_spawn(Box::pin(async move {
                let _held = held;
                started.fetch_add(1, Ordering::AcqRel);
                std::future::pending::<()>().await;
            })));
        }
        until(|| started.load(Ordering::Acquire) == JOBS);
        assert_eq!(pool.slots.available_permits(), 0);
        assert!(!pool.try_spawn(Box::pin(std::future::pending())));
        stop.request_stop();
        drop(pool);
        assert_eq!(dropped.load(Ordering::Acquire), JOBS);
    }

    #[test]
    fn immediate_completions_return_permits_without_accumulating_live_jobs() {
        let fixture = Fixture::new();
        let (pool, _) = fixture.pool();
        let completed = Arc::new(AtomicUsize::new(0));
        for _ in 0..256 {
            until(|| {
                let completed = completed.clone();
                pool.try_spawn(Box::pin(async move {
                    completed.fetch_add(1, Ordering::AcqRel);
                }))
            });
        }
        until(|| completed.load(Ordering::Acquire) == 256);
        until(|| pool.slots.available_permits() == JOBS);
        drop(pool);
    }

    #[test]
    fn non_yielding_job_does_not_block_the_main_current_thread_reactor() {
        let fixture = Fixture::new();
        let (pool, _) = fixture.pool();
        let entered = Arc::new(AtomicBool::new(false));
        let release = Arc::new(AtomicBool::new(false));
        let job_entered = entered.clone();
        let job_release = release.clone();
        assert!(pool.try_spawn(Box::pin(async move {
            job_entered.store(true, Ordering::Release);
            let deadline = Instant::now() + Duration::from_secs(5);
            while !job_release.load(Ordering::Acquire) && Instant::now() < deadline {
                std::hint::spin_loop();
            }
        })));
        until(|| entered.load(Ordering::Acquire));
        tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap().block_on(async {
            tokio::time::timeout(Duration::from_secs(1), tokio::time::sleep(Duration::from_millis(10)))
                .await.unwrap();
        });
        assert_eq!(pool.slots.available_permits(), JOBS - 1);
        release.store(true, Ordering::Release);
        drop(pool);
    }

    #[test]
    fn drop_joins_non_yielding_work_before_releasing_instance_guard() {
        let fixture = Fixture::new();
        let guard = fixture.guard();
        let weak = Arc::downgrade(&guard);
        let stop = Lifecycle::new(Arc::new(AtomicBool::new(false)), 5);
        let pool = Pool::start(guard, stop.clone()).unwrap();
        let entered = Arc::new(AtomicBool::new(false));
        let release = Arc::new(AtomicBool::new(false));
        let exited = Arc::new(AtomicUsize::new(0));
        let job_entered = entered.clone();
        let job_release = release.clone();
        let on_exit = CountDrop(exited.clone());
        assert!(pool.try_spawn(Box::pin(async move {
            let _on_exit = on_exit;
            job_entered.store(true, Ordering::Release);
            let deadline = Instant::now() + Duration::from_secs(5);
            while !job_release.load(Ordering::Acquire) && Instant::now() < deadline {
                std::hint::spin_loop();
            }
        })));
        until(|| entered.load(Ordering::Acquire));
        stop.request_stop();
        let (finished, done) = mpsc::sync_channel(1);
        let dropper = std::thread::spawn(move || {
            drop(pool);
            finished.send(()).unwrap();
        });
        assert!(done.recv_timeout(Duration::from_millis(30)).is_err());
        assert!(weak.upgrade().is_some());
        release.store(true, Ordering::Release);
        dropper.join().unwrap();
        done.recv_timeout(Duration::from_secs(1)).unwrap();
        assert_eq!(exited.load(Ordering::Acquire), 1);
        assert!(weak.upgrade().is_none());
    }

    struct SlowDrop {
        entered: Arc<AtomicBool>,
        release: Arc<AtomicBool>,
    }
    impl Future for SlowDrop {
        type Output = ();
        fn poll(self: Pin<&mut Self>, _: &mut Context<'_>) -> Poll<()> {
            Poll::Pending
        }
    }
    impl Drop for SlowDrop {
        fn drop(&mut self) {
            self.entered.store(true, Ordering::Release);
            let deadline = Instant::now() + Duration::from_secs(5);
            while !self.release.load(Ordering::Acquire) && Instant::now() < deadline {
                std::hint::spin_loop();
            }
        }
    }
    #[test]
    fn admission_permit_is_held_through_the_actual_future_destructor() {
        let fixture = Fixture::new();
        let (pool, stop) = fixture.pool();
        let slots = pool.slots.clone();
        let entered = Arc::new(AtomicBool::new(false));
        let release = Arc::new(AtomicBool::new(false));
        assert!(pool.try_spawn(Box::pin(SlowDrop { entered: entered.clone(), release: release.clone() })));
        stop.request_stop();
        until(|| entered.load(Ordering::Acquire));
        assert_eq!(slots.available_permits(), JOBS - 1);
        release.store(true, Ordering::Release);
        until(|| slots.available_permits() == JOBS);
        drop(pool);
    }

    struct ObserveStoppedDrop {
        lifecycle: Arc<Lifecycle>,
        observed: Arc<AtomicBool>,
    }
    impl Future for ObserveStoppedDrop {
        type Output = ();
        fn poll(self: Pin<&mut Self>, _: &mut Context<'_>) -> Poll<()> {
            Poll::Pending
        }
    }
    impl Drop for ObserveStoppedDrop {
        fn drop(&mut self) {
            self.observed.store(
                self.lifecycle.while_running(|| ()).is_none(),
                Ordering::Release,
            );
        }
    }
    #[test]
    fn pool_drop_stops_activation_before_discarding_jobs() {
        let fixture = Fixture::new();
        let (pool, lifecycle) = fixture.pool();
        let observed = Arc::new(AtomicBool::new(false));
        assert!(lifecycle.while_running(|| ()).is_some());
        assert!(pool.try_spawn(Box::pin(ObserveStoppedDrop {
            lifecycle: lifecycle.clone(),
            observed: observed.clone(),
        })));
        drop(pool);
        assert!(observed.load(Ordering::Acquire));
        assert!(lifecycle.while_running(|| ()).is_none());
    }

    #[test]
    fn job_panic_requests_global_stop_and_refuses_further_dispatch() {
        let fixture = Fixture::new();
        let (pool, stop) = fixture.pool();
        assert!(pool.try_spawn(Box::pin(async { panic!("TLS executor finite test panic") })));
        until(|| stop.stop.load(Ordering::Acquire));
        assert!(stop.while_running(|| ()).is_none());
        assert!(!pool.try_spawn(Box::pin(async {})));
        drop(pool);
    }

    #[test]
    fn already_stopping_start_preserves_the_callers_guard_without_threads() {
        let fixture = Fixture::new();
        let guard = fixture.guard();
        let stop = Lifecycle::new(Arc::new(AtomicBool::new(false)), 5);
        stop.request_stop();
        assert!(Pool::start(guard.clone(), stop).is_err());
        assert_eq!(Arc::strong_count(&guard), 1);
        assert!(guard.validate().is_ok());
    }
}
