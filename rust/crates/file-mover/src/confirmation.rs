//! Admin confirmation proofs (API-CONTRACT-CLOSEOUT.md "Confirmation, reads and
//! forgetting"; ROUTE-SCHEMAS "Bounded list and confirmation read proposal").
//!
//! A proof authorizes one action on one exact ordered selection for five
//! minutes. It binds the state instance, the authenticated account principal,
//! the session revocation generation (so logout or account activation voids it),
//! the action and the ordered job IDs, under an HMAC-SHA256 key that exists only
//! in this process (a restart voids every proof). It is authorization context,
//! not proof that a person inspected anything, and it stores nothing.
//!
//! Wire form: `c1.<expires_at>.<64 lowercase hex>`; within the contract's
//! `^[A-Za-z0-9_.-]+$`, 16..6144 bytes.
use subtle::ConstantTimeEq;
use zeroize::Zeroizing;

pub(crate) const LIFETIME_SECONDS: i64 = 300;
const BLOCK: usize = 64;

/// What a proof is bound to, other than its expiry.
pub(crate) struct Scope<'a> {
    pub(crate) instance: &'a str,
    pub(crate) principal: &'a str,
    pub(crate) generation: u64,
    pub(crate) action: &'a str,
    pub(crate) job_ids: &'a [i64],
}

/// Action-specific authenticated binding carried in the token: `-` for none,
/// or the 64-hex fingerprint of the exact deletable selection (delete-data).
pub(crate) const NO_BINDING: &str = "-";
fn valid_binding(b: &str) -> bool {
    b == NO_BINDING
        || (b.len() == 64
            && b.bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c)))
}

pub(crate) struct Key(Zeroizing<[u8; 32]>);
impl Key {
    /// A fresh random key; None if the system random source fails.
    pub(crate) fn generate() -> Option<Self> {
        let mut key = Zeroizing::new([0_u8; 32]);
        crate::tls::provider()
            .secure_random
            .fill(key.as_mut())
            .ok()?;
        Some(Self(key))
    }
    #[cfg(test)]
    fn fixed(bytes: [u8; 32]) -> Self {
        Self(Zeroizing::new(bytes))
    }
}

fn sha256(bytes: &[u8]) -> [u8; 32] {
    let hex = mover_fs::sha256_hex(bytes);
    let mut out = [0_u8; 32];
    for (i, b) in out.iter_mut().enumerate() {
        *b = u8::from_str_radix(&hex[2 * i..2 * i + 2], 16).expect("sha256 hex");
    }
    out
}

/// HMAC-SHA256 (RFC 2104) for keys of at most one block.
fn hmac(key: &[u8], message: &[u8]) -> [u8; 32] {
    debug_assert!(key.len() <= BLOCK);
    let mut inner = Zeroizing::new(Vec::with_capacity(BLOCK + message.len()));
    let mut outer = Zeroizing::new(Vec::with_capacity(BLOCK + 32));
    for i in 0..BLOCK {
        let k = key.get(i).copied().unwrap_or(0);
        inner.push(k ^ 0x36);
        outer.push(k ^ 0x5c);
    }
    inner.extend_from_slice(message);
    outer.extend_from_slice(&sha256(&inner));
    sha256(&outer)
}

fn frame(scope: &Scope<'_>, high_water: i64, binding: &str, expires_at: i64) -> Vec<u8> {
    let mut f = b"BFM-CONFIRMATION\0v1\0".to_vec();
    for text in [scope.instance, scope.principal, scope.action] {
        f.extend_from_slice(&(text.len() as u32).to_be_bytes());
        f.extend_from_slice(text.as_bytes());
    }
    f.extend_from_slice(&scope.generation.to_be_bytes());
    f.extend_from_slice(&(scope.job_ids.len() as u16).to_be_bytes());
    for id in scope.job_ids {
        f.extend_from_slice(&id.to_be_bytes());
    }
    f.extend_from_slice(&high_water.to_be_bytes());
    f.extend_from_slice(&(binding.len() as u32).to_be_bytes());
    f.extend_from_slice(binding.as_bytes());
    f.extend_from_slice(&expires_at.to_be_bytes());
    f
}

fn canonical(text: &str) -> Option<i64> {
    text.parse::<i64>()
        .ok()
        .filter(|n| *n >= 0 && n.to_string() == text)
}

/// Issue a proof valid until `now + LIFETIME_SECONDS`. `high_water` is the
/// job-ID high-water mark at issuance: IDs above it were never allocated when
/// the operator confirmed, so the proof can never cover a later job.
pub(crate) fn issue(
    key: &Key,
    scope: &Scope<'_>,
    high_water: i64,
    binding: &str,
    now: i64,
) -> (String, i64) {
    assert!(valid_binding(binding), "confirmation binding");
    let expires_at = now.saturating_add(LIFETIME_SECONDS);
    let mac = hmac(
        key.0.as_ref(),
        &frame(scope, high_water, binding, expires_at),
    );
    let hex: String = mac.iter().map(|b| format!("{b:02x}")).collect();
    (
        format!("c1.{expires_at}.{high_water}.{binding}.{hex}"),
        expires_at,
    )
}

/// Verify an unchanged proof for exactly this scope at `now`, returning the
/// authenticated issuance high-water mark and binding. Any difference (scope,
/// tampering, expiry, encoding) is the same refusal.
pub(crate) fn verify(key: &Key, token: &str, scope: &Scope<'_>, now: i64) -> Option<(i64, String)> {
    let mut parts = token.strip_prefix("c1.")?.split('.');
    let (expires, high_water, binding, mac) =
        (parts.next()?, parts.next()?, parts.next()?, parts.next()?);
    if !valid_binding(binding) {
        return None;
    }
    if parts.next().is_some() {
        return None;
    }
    let expires_at = canonical(expires)?;
    let high_water = canonical(high_water)?;
    if expires_at <= now
        || expires_at > now.saturating_add(LIFETIME_SECONDS)
        || mac.len() != 64
        || !mac
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return None;
    }
    let expected = hmac(
        key.0.as_ref(),
        &frame(scope, high_water, binding, expires_at),
    );
    let expected: String = expected.iter().map(|b| format!("{b:02x}")).collect();
    bool::from(expected.as_bytes().ct_eq(mac.as_bytes())).then(|| (high_water, binding.to_owned()))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn hex(bytes: &[u8]) -> String {
        bytes.iter().map(|b| format!("{b:02x}")).collect()
    }

    #[test]
    fn hmac_matches_rfc4231() {
        // Test case 1.
        assert_eq!(
            hex(&hmac(&[0x0b; 20], b"Hi There")),
            "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"
        );
        // Test case 2.
        assert_eq!(
            hex(&hmac(b"Jefe", b"what do ya want for nothing?")),
            "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"
        );
    }

    #[test]
    fn proofs_bind_scope_order_and_expiry() {
        let key = Key::fixed([7; 32]);
        let ids = [3, 1, 3];
        let scope = Scope {
            instance: "i",
            principal: "p",
            generation: 4,
            action: "cancel",
            job_ids: &ids,
        };
        let (token, expires) = issue(&key, &scope, 41, NO_BINDING, 1000);
        assert_eq!(expires, 1300);
        assert!(
            token.len() >= 16
                && token
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"_.-".contains(&b))
        );
        assert_eq!(
            verify(&key, &token, &scope, 1000),
            Some((41, NO_BINDING.to_owned()))
        );
        assert_eq!(
            verify(&key, &token, &scope, 1299),
            Some((41, NO_BINDING.to_owned()))
        );
        assert_eq!(verify(&key, &token, &scope, 1300), None, "expired");
        assert_eq!(
            verify(&key, &token, &scope, 900),
            None,
            "issued in the future"
        );
        // The high-water mark is authenticated, not editable.
        assert_eq!(
            verify(&key, &token.replacen(".41.", ".42.", 1), &scope, 1000),
            None
        );
        let changed = |f: &dyn Fn(&mut Scope<'_>)| {
            let mut s = Scope {
                job_ids: &ids,
                ..scope
            };
            f(&mut s);
            verify(&key, &token, &s, 1000).is_some()
        };
        assert!(!changed(&|s| s.instance = "other"));
        assert!(!changed(&|s| s.principal = "other"));
        assert!(!changed(&|s| s.generation = 5));
        assert!(!changed(&|s| s.action = "clear-history"));
        assert!(!changed(&|s| s.job_ids = &[1, 3, 3]));
        assert!(!changed(&|s| s.job_ids = &[3, 1]));
        assert!(
            verify(&Key::fixed([8; 32]), &token, &scope, 1000).is_none(),
            "other process"
        );
        // The binding is authenticated: a different fingerprint is refused.
        let bound = "a".repeat(64);
        let (with, _) = issue(&key, &scope, 41, &bound, 1000);
        assert_eq!(verify(&key, &with, &scope, 1000), Some((41, bound.clone())));
        assert_eq!(
            verify(
                &key,
                &with.replacen(&bound, &"b".repeat(64), 1),
                &scope,
                1000
            ),
            None
        );
        assert_eq!(
            verify(&key, &with.replacen(&bound, "-", 1), &scope, 1000),
            None
        );
        for bad in [
            token.replacen("c1.", "c2.", 1),
            token.replacen("1300", "01300", 1),
            token.replacen("1300", "1301", 1),
            token.to_uppercase(),
            format!("{token}0"),
            String::new(),
        ] {
            assert!(verify(&key, &bad, &scope, 1000).is_none(), "{bad}");
        }
    }
}
