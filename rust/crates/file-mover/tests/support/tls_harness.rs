// Test binary policy, shared by proof, producer TLS and admin TLS cases. Keeping
// this inside the binary also caps direct libtest, CI and SLES invocations.
use std::{io::Write, sync::{Condvar, Mutex, OnceLock}, time::Duration};
const PARALLEL: usize = 2;
static ACTIVE: Mutex<usize> = Mutex::new(0);
static AVAILABLE: Condvar = Condvar::new();
static SCALE: OnceLock<u32> = OnceLock::new();
pub struct Slot;
pub fn enter() -> Slot {
    let _ = scale();
    let mut active = ACTIVE.lock().unwrap_or_else(|p| p.into_inner());
    while *active >= PARALLEL {
        active = AVAILABLE.wait(active).unwrap_or_else(|p| p.into_inner());
    }
    *active += 1;
    Slot
}
impl Drop for Slot {
    fn drop(&mut self) {
        let mut active = ACTIVE.lock().unwrap_or_else(|p| p.into_inner());
        *active -= 1;
        AVAILABLE.notify_one();
    }
}
fn parse_scale(value: &str) -> Result<u32, &'static str> {
    value.parse::<u32>().ok().filter(|n| (1..=8).contains(n))
        .ok_or("FILE_MOVER_TEST_TLS_TIMEOUT_SCALE must be an integer from 1 through 8")
}
fn scale() -> u32 {
    *SCALE.get_or_init(|| {
        // Two-thread runs still failed 1/32 on the reported eight-core WSL
        // host. Default to 2x client I/O margin; use 1 for baseline comparisons.
        let scale = match std::env::var("FILE_MOVER_TEST_TLS_TIMEOUT_SCALE") {
            Ok(value) => parse_scale(&value).expect("invalid TLS test timeout scale"),
            Err(std::env::VarError::NotPresent) => 2,
            Err(_) => panic!("TLS test timeout scale must be UTF-8"),
        };
        let _ = writeln!(std::io::stderr(), "TLS_TEST_HARNESS parallel_cap={PARALLEL} client_timeout_scale={scale}; product deadlines unchanged");
        scale
    })
}
pub fn client_timeout(base: Duration) -> Duration { base * scale() }
pub fn client_error(error: std::io::Error) -> String {
    assert!(!matches!(error.kind(), std::io::ErrorKind::TimedOut | std::io::ErrorKind::WouldBlock),
        "timeout is not refusal evidence: {error}");
    error.to_string()
}
#[test]
fn scale_validation_is_bounded_and_explicit() {
    assert_eq!(parse_scale("1"), Ok(1));
    assert_eq!(parse_scale("8"), Ok(8));
    for value in ["0", "9", "-1", "1.5", "", "abc"] { assert!(parse_scale(value).is_err()); }
}
#[test]
fn timeouts_still_fail_instead_of_becoming_refusal_results() {
    for kind in [std::io::ErrorKind::TimedOut, std::io::ErrorKind::WouldBlock] {
        assert!(std::panic::catch_unwind(|| client_error(std::io::Error::from(kind))).is_err());
    }
    assert!(!client_error(std::io::Error::from(std::io::ErrorKind::ConnectionReset)).is_empty());
}
