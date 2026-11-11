//! Bounded admin password primitive. No listener, account file or session activation.
//! Synchronous hashing must run on an owned worker, never the async/control runtime.
use argon2::{
    Algorithm, Argon2, Params, Version,
    password_hash::{PasswordHash, PasswordHasher, PasswordVerifier, SaltString},
};
use zeroize::Zeroizing;

const MEMORY_KIB: u32 = 19_456;
const ITERATIONS: u32 = 2;
const LANES: u32 = 1;
const TAG_BYTES: usize = 32;
const SALT_BYTES: usize = 16;
const MAX_PASSWORD: usize = 4096;
const MAX_PHC: usize = 256;

/// Fixed messages deliberately contain no password, verifier, path or username.
#[derive(Debug, PartialEq, Eq)]
pub enum Error {
    InvalidPassword,
    InvalidUsername,
    UnsupportedVerifier,
    EntropyUnavailable,
    HashFailure,
}

/// Owned input is cleared on drop. Caller must bound its transport allocation.
/// No Debug/Display/Serialize/Clone: do not accidentally emit or duplicate secrets.
pub struct Password(Zeroizing<Vec<u8>>);
impl Password {
    pub fn new(bytes: Vec<u8>) -> Result<Self, Error> {
        let bytes = Zeroizing::new(bytes);
        if bytes.is_empty() || bytes.len() > MAX_PASSWORD || std::str::from_utf8(&bytes).is_err() {
            return Err(Error::InvalidPassword);
        }
        Ok(Self(bytes))
    }
}

pub fn validate_username(username: &str) -> Result<(), Error> {
    if username.is_empty() || username.len() > 128 {
        Err(Error::InvalidUsername)
    } else {
        Ok(())
    }
}

/// Opaque credential bytes: expose explicitly only to a future guarded writer.
/// Not an account record; storing these bytes alone does not provision an account.
pub struct Verifier(Zeroizing<String>);
impl Verifier {
    pub fn create(password: &Password) -> Result<Self, Error> {
        Self::create_with_entropy(password, |bytes| {
            crate::tls::provider()
                .secure_random
                .fill(bytes)
                .map_err(|_| Error::EntropyUnavailable)
        })
    }

    fn create_with_entropy(
        password: &Password,
        entropy: impl FnOnce(&mut [u8]) -> Result<(), Error>,
    ) -> Result<Self, Error> {
        let mut salt = Zeroizing::new([0_u8; SALT_BYTES]);
        entropy(salt.as_mut())?;
        let salt = SaltString::encode_b64(salt.as_ref()).map_err(|_| Error::HashFailure)?;
        let encoded = engine()?
            .hash_password(&password.0, &salt)
            .map_err(|_| Error::HashFailure)?
            .to_string();
        Self::from_encoded(encoded)
    }

    /// Reject foreign algorithms/costs *before* any expensive verifier work.
    pub fn from_encoded(encoded: String) -> Result<Self, Error> {
        let encoded = Zeroizing::new(encoded);
        if encoded.len() > MAX_PHC || !encoded.is_ascii() {
            return Err(Error::UnsupportedVerifier);
        }
        let parsed = PasswordHash::new(&encoded).map_err(|_| Error::UnsupportedVerifier)?;
        if parsed.algorithm.as_str() != "argon2id"
            || parsed.version != Some(19)
            || parsed.params.to_string() != "m=19456,t=2,p=1"
            || parsed.hash.as_ref().map(|h| h.as_bytes().len()) != Some(TAG_BYTES)
        {
            return Err(Error::UnsupportedVerifier);
        }
        let salt = parsed.salt.ok_or(Error::UnsupportedVerifier)?;
        let mut decoded = Zeroizing::new([0_u8; 64]);
        let bytes = salt
            .decode_b64(decoded.as_mut())
            .map_err(|_| Error::UnsupportedVerifier)?;
        if bytes.len() != SALT_BYTES
            || SaltString::encode_b64(bytes)
                .map_err(|_| Error::UnsupportedVerifier)?
                .as_str()
                != salt.as_str()
            || parsed.to_string() != *encoded
        {
            return Err(Error::UnsupportedVerifier);
        }
        Ok(Self(encoded))
    }

    pub fn encoded(&self) -> &str {
        &self.0
    }

    pub fn verify(&self, password: &Password) -> Result<bool, Error> {
        // Construction already admitted only our exact bounded profile. Library
        // verifies the derived tag with password-hash's constant-time comparison.
        let parsed = PasswordHash::new(&self.0).map_err(|_| Error::UnsupportedVerifier)?;
        match engine()?.verify_password(&password.0, &parsed) {
            Ok(()) => Ok(true),
            Err(argon2::password_hash::Error::Password) => Ok(false),
            Err(_) => Err(Error::HashFailure),
        }
    }
}

fn engine() -> Result<Argon2<'static>, Error> {
    let params = Params::new(MEMORY_KIB, ITERATIONS, LANES, Some(TAG_BYTES))
        .map_err(|_| Error::HashFailure)?;
    Ok(Argon2::new(Algorithm::Argon2id, Version::V0x13, params))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn password(s: &str) -> Password {
        Password::new(s.as_bytes().to_vec()).unwrap()
    }

    #[test]
    fn input_boundaries_preserve_exact_utf8() {
        assert!(matches!(Password::new(vec![]), Err(Error::InvalidPassword)));
        assert!(Password::new(vec![b'a'; 4096]).is_ok());
        assert!(matches!(
            Password::new(vec![b'a'; 4097]),
            Err(Error::InvalidPassword)
        ));
        assert!(matches!(
            Password::new(vec![0xff]),
            Err(Error::InvalidPassword)
        ));
        assert!(validate_username("").is_err());
        assert!(validate_username(&"x".repeat(128)).is_ok());
        assert!(validate_username(&"é".repeat(65)).is_err());
        assert!(validate_username(" admin ").is_ok());
        let verifier = Verifier::create(&password(" café \n")).unwrap();
        assert!(verifier.verify(&password(" café \n")).unwrap());
        assert!(!verifier.verify(&password("café")).unwrap());
        assert!(!verifier.verify(&password(" cafe\u{301} \n")).unwrap());
    }

    #[test]
    fn roundtrip_wrong_password_and_independent_salts() {
        let input = password("disposable proof password");
        let a = Verifier::create(&input).unwrap();
        let b = Verifier::create(&input).unwrap();
        assert_ne!(a.encoded(), b.encoded());
        let reopened = Verifier::from_encoded(a.encoded().to_owned()).unwrap();
        assert!(reopened.verify(&input).unwrap());
        assert!(!reopened.verify(&password("wrong")).unwrap());
    }

    #[test]
    fn malformed_or_expensive_records_refuse_before_hashing() {
        let valid = Verifier::create(&password("fixture")).unwrap();
        let text = valid.encoded();
        for bad in [
            "".to_owned(),
            "x".repeat(257),
            text.replace("argon2id", "argon2i"),
            text.replace("v=19", "v=16"),
            text.replace("19456", "4294967295"),
            text.replace("t=2", "t=4294967295"),
            text.replace("p=1", "p=2"),
            text.replace("m=19456,t=2,p=1", "t=2,m=19456,p=1"),
            text.replace("p=1", "p=1,keyid=AA"),
            format!("{text}="),
            text.replace(text.split('$').nth(4).unwrap(), "c2hvcnQ"),
        ] {
            assert!(matches!(
                Verifier::from_encoded(bad),
                Err(Error::UnsupportedVerifier)
            ));
        }
    }

    #[test]
    fn entropy_failure_never_returns_a_verifier() {
        assert!(matches!(
            Verifier::create_with_entropy(&password("fixture"), |_| Err(Error::EntropyUnavailable)),
            Err(Error::EntropyUnavailable)
        ));
    }

    #[test]
    fn rfc_9106_argon2id_known_answer() {
        // RFC 9106 section 5.3. This library KAT deliberately uses the RFC's
        // small test profile; Verifier admission above still rejects it.
        let params = argon2::ParamsBuilder::new()
            .m_cost(32)
            .t_cost(3)
            .p_cost(4)
            .data(argon2::AssociatedData::new(&[4_u8; 12]).unwrap())
            .build()
            .unwrap();
        let hash = Argon2::new_with_secret(&[3_u8; 8], Algorithm::Argon2id, Version::V0x13, params)
            .unwrap();
        let mut out = [0_u8; 32];
        hash.hash_password_into(&[1_u8; 32], &[2_u8; 16], &mut out)
            .unwrap();
        assert_eq!(
            out,
            [
                0x0d, 0x64, 0x0d, 0xf5, 0x8d, 0x78, 0x76, 0x6c, 0x08, 0xc0, 0x37, 0xa3, 0x4a, 0x8b,
                0x53, 0xc9, 0xd0, 0x1e, 0xf0, 0x45, 0x2d, 0x75, 0xb6, 0x5e, 0xb5, 0x25, 0x20, 0xe9,
                0x6b, 0x01, 0xe6, 0x59,
            ]
        );
    }

    #[test]
    fn maximum_password_is_not_truncated() {
        let mut bytes = vec![b'x'; MAX_PASSWORD];
        let verifier = Verifier::create(&Password::new(bytes.clone()).unwrap()).unwrap();
        bytes[MAX_PASSWORD - 1] = b'y';
        assert!(!verifier.verify(&Password::new(bytes).unwrap()).unwrap());
    }

    #[test]
    fn measured_fixed_profile_hash_and_verify() {
        let start = std::time::Instant::now();
        let input = password("disposable SLES timing fixture");
        let verifier = Verifier::create(&input).unwrap();
        let hashed = start.elapsed();
        assert!(verifier.verify(&input).unwrap());
        println!(
            "ADMIN_PASSWORD_PROOF memory_kib={MEMORY_KIB} iterations={ITERATIONS} lanes={LANES} hash_ms={} total_ms={}",
            hashed.as_millis(),
            start.elapsed().as_millis()
        );
        let status = std::fs::read_to_string("/proc/self/status").unwrap();
        let high_water = status
            .lines()
            .find(|line| line.starts_with("VmHWM:"))
            .unwrap();
        println!("ADMIN_PASSWORD_PROCESS_HIGH_WATER {high_water}");
        // Timing is evidence, not a scheduler/CPU deadline assertion. Production
        // worker admission/control responsiveness belongs to the later integration.
    }
}
