//! Private, bounded diagnostics. Never an effect receipt or retry authorization.
pub(crate) fn describe(error: &(dyn std::error::Error + 'static)) -> String {
    mover_fs::failure_diagnostic(error)
}
pub(crate) fn valid(detail: &str) -> bool {
    detail.len() <= 240 && detail.bytes().all(|c| c.is_ascii_graphic() || c == b' ')
}

#[cfg(test)]
mod tests {
    #[test]
    fn diagnostic_is_bounded_and_does_not_echo_arbitrary_errors() {
        let e: Box<dyn std::error::Error> = "secret/path\nforged log".into();
        assert_eq!(super::describe(e.as_ref()), "blocked_or_uncertain");
        let e = mover_fs::ClaimError::Blocked("custody changed");
        assert_eq!(super::describe(&e), "blocked: custody changed");
        assert!(super::valid(&super::describe(&e)));
        assert!(!super::valid("injected\nlog"));
        assert!(!super::valid(&"x".repeat(241)));
    }
}
