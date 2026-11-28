// Explicit local convenience only; never qualification evidence or a fallback
// for supplied-but-broken executables/certificates. No environment mutation.
use std::{ffi::OsStr, io::Write};
const OPTIONAL: &str = "FILE_MOVER_TEST_OPTIONAL_FIXTURES";
const REQUIRED: &str = "FILE_MOVER_TEST_REQUIRE_FIXTURES";
fn skip(missing: bool, optional: Option<&OsStr>, required: Option<&OsStr>) -> Result<bool, &'static str> {
    if optional.is_some_and(|value| value != "1") || required.is_some_and(|value| value != "1") {
        return Err("fixture mode flags must be unset or exactly 1");
    }
    if required.is_some() && optional.is_some() {
        return Err("optional fixture skips are forbidden in qualification");
    }
    if !missing { return Ok(false); }
    if optional.is_some() { Ok(true) } else { Err("required test fixtures are missing; supply them or explicitly select local optional-fixture mode") }
}
pub fn ready(test: &str, inputs: &[&str]) -> bool {
    let missing: Vec<_> = inputs.iter().copied().filter(|name| std::env::var_os(name).is_none()).collect();
    for name in inputs {
        assert!(!std::env::var_os(name).is_some_and(|value| value.is_empty()), "supplied test fixture variable is empty: {name}");
    }
    available(test, &missing.join(","), missing.is_empty())
}
/// Host fixtures (not environment variables) obey the same explicit local-only
/// skip policy. A missing mount fixture must still fail qualification.
pub fn available(test: &str, fixture: &str, present: bool) -> bool {
    let optional = std::env::var_os(OPTIONAL);
    let required = std::env::var_os(REQUIRED);
    let skip = skip(!present, optional.as_deref(), required.as_deref())
        .unwrap_or_else(|reason| panic!("test fixture prerequisite: test={test} fixture={fixture}: {reason}"));
    if skip {
        // Direct stderr bypasses libtest's successful-test capture. Return-based
        // skips still appear passed in libtest; this marker must stay visible.
        writeln!(std::io::stderr(), "SKIP_FIXTURE test={test} missing={fixture} mode=explicit-local NOT_QUALIFICATION").expect("write local fixture skip notice");
        false
    } else { true }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn skips_require_explicit_local_mode_and_actual_absence() {
        assert!(ready("prerequisite_policy_no_inputs", &[]));
        assert_eq!(skip(true, Some(OsStr::new("1")), None), Ok(true));
        assert_eq!(skip(false, Some(OsStr::new("1")), None), Ok(false));
        assert!(skip(true, None, None).is_err());
        assert!(skip(true, None, Some(OsStr::new("1"))).is_err());
        assert_eq!(skip(false, None, Some(OsStr::new("1"))), Ok(false));
    }
    #[test]
    fn qualification_cannot_enable_optional_skips_even_with_complete_inputs() {
        for missing in [false, true] {
            assert!(skip(missing, Some(OsStr::new("1")), Some(OsStr::new("1"))).is_err());
        }
        assert!(skip(true, Some(OsStr::new("0")), None).is_err());
    }
}
