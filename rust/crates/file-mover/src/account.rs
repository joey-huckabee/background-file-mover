//! Strict account record and offline secret input. No sessions or remote auth.
use crate::password::{Password, Verifier, validate_username};
use serde::{Deserialize, Deserializer, Serialize};
use subtle::ConstantTimeEq;
use zeroize::Zeroizing;

pub const MAX_INPUT: usize = 65_536;
pub const MAX_RECORD: usize = 8192;
pub struct SecretText(pub Zeroizing<String>);
impl<'de> Deserialize<'de> for SecretText {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        String::deserialize(d).map(|s| Self(Zeroizing::new(s)))
    }
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct InitInput {
    username: SecretText,
    password: SecretText,
    confirm_password: SecretText,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ChangeInput {
    password: SecretText,
    confirm_password: SecretText,
}
pub struct NewCredentials {
    pub username: Option<String>,
    pub password: Password,
}
impl NewCredentials {
    pub fn encode_for_worker(&self) -> Result<Zeroizing<Vec<u8>>, &'static str> {
        #[derive(Serialize)]
        struct Message<'a> {
            #[serde(skip_serializing_if = "Option::is_none")]
            username: Option<&'a str>,
            password: &'a str,
            confirm_password: &'a str,
        }
        let password = std::str::from_utf8(self.password.expose_for_local_transport())
            .map_err(|_| "invalid password UTF-8")?;
        let bytes = Zeroizing::new(
            serde_json::to_vec(&Message {
                username: self.username.as_deref(),
                password,
                confirm_password: password,
            })
            .map_err(|_| "account transport encoding failed")?,
        );
        if bytes.len() > MAX_INPUT {
            return Err("account transport exceeds bound");
        }
        Ok(bytes)
    }
    pub fn decode(bytes: &[u8], initialize: bool) -> Result<Self, &'static str> {
        if bytes.len() > MAX_INPUT {
            return Err("account input exceeds bound");
        }
        if initialize {
            let input: InitInput =
                serde_json::from_slice(bytes).map_err(|_| "invalid account input object")?;
            Self::from_text(
                Some(input.username),
                input.password,
                input.confirm_password,
                true,
            )
        } else {
            let input: ChangeInput =
                serde_json::from_slice(bytes).map_err(|_| "invalid account input object")?;
            Self::from_text(None, input.password, input.confirm_password, false)
        }
    }
    pub fn from_text(
        username: Option<SecretText>,
        password: SecretText,
        confirm: SecretText,
        initialize: bool,
    ) -> Result<Self, &'static str> {
        if initialize != username.is_some() {
            return Err("username required only for account initialization");
        }
        let username = if let Some(u) = username {
            validate_username(&u.0).map_err(|_| "invalid username byte length")?;
            Some(u.0.to_string())
        } else {
            None
        };
        if !bool::from(password.0.as_bytes().ct_eq(confirm.0.as_bytes())) {
            return Err("new passwords do not match");
        }
        let password = Password::new(password.0.as_bytes().to_vec())
            .map_err(|_| "invalid password byte length or UTF-8")?;
        Ok(Self { username, password })
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RawRecord {
    version: u32,
    instance_id: String,
    account_id: String,
    username: String,
    revision: u64,
    verifier: SecretText,
}
pub struct Record {
    pub instance_id: String,
    pub account_id: String,
    pub username: String,
    pub revision: u64,
    verifier: Verifier,
}
impl Record {
    pub fn decode(bytes: &[u8], instance: &str) -> Result<Self, &'static str> {
        if bytes.len() > MAX_RECORD {
            return Err("account record exceeds bound");
        }
        let raw: RawRecord = serde_json::from_slice(bytes).map_err(|_| "invalid account record")?;
        if raw.version != 1
            || raw.instance_id != instance
            || raw.revision == 0
            || raw.account_id.len() != 64
            || !raw
                .account_id
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
            || validate_username(&raw.username).is_err()
        {
            return Err("unsupported or foreign account record");
        }
        let verifier = Verifier::from_encoded(raw.verifier.0.to_string())
            .map_err(|_| "unsupported account password verifier")?;
        Ok(Self {
            instance_id: raw.instance_id,
            account_id: raw.account_id,
            username: raw.username,
            revision: raw.revision,
            verifier,
        })
    }
    pub fn create(
        instance: &str,
        username: String,
        password: &Password,
    ) -> Result<Self, &'static str> {
        validate_username(&username).map_err(|_| "invalid username")?;
        let mut id = Zeroizing::new([0u8; 32]);
        crate::tls::provider()
            .secure_random
            .fill(id.as_mut())
            .map_err(|_| "account entropy unavailable")?;
        let account_id = id.iter().map(|b| format!("{b:02x}")).collect();
        let verifier = Verifier::create(password).map_err(|_| "account password hashing failed")?;
        Ok(Self {
            instance_id: instance.into(),
            account_id,
            username,
            revision: 1,
            verifier,
        })
    }
    pub fn replace_password(&self, password: &Password) -> Result<Self, &'static str> {
        let revision = self
            .revision
            .checked_add(1)
            .ok_or("account revision exhausted")?;
        let verifier = Verifier::create(password).map_err(|_| "account password hashing failed")?;
        Ok(Self {
            instance_id: self.instance_id.clone(),
            account_id: self.account_id.clone(),
            username: self.username.clone(),
            revision,
            verifier,
        })
    }
    pub fn encode(&self) -> Result<Zeroizing<Vec<u8>>, &'static str> {
        #[derive(Serialize)]
        struct Output<'a> {
            version: u32,
            instance_id: &'a str,
            account_id: &'a str,
            username: &'a str,
            revision: u64,
            verifier: &'a str,
        }
        let bytes = Zeroizing::new(
            serde_json::to_vec(&Output {
                version: 1,
                instance_id: &self.instance_id,
                account_id: &self.account_id,
                username: &self.username,
                revision: self.revision,
                verifier: self.verifier.encoded(),
            })
            .map_err(|_| "account encoding failed")?,
        );
        if bytes.len() > MAX_RECORD {
            return Err("account record exceeds bound");
        }
        Ok(bytes)
    }
    pub fn status(&self) -> serde_json::Value {
        serde_json::json!({"provisioned":true,"version":1,"username":self.username,"revision":self.revision.to_string()})
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn pw(s: &str) -> Password {
        Password::new(s.as_bytes().to_vec()).unwrap()
    }
    #[test]
    fn input_is_strict_bounded_and_never_renames() {
        assert!(
            NewCredentials::decode(
                br#"{"username":" admin ","password":" p ","confirm_password":" p "}"#,
                true
            )
            .is_ok()
        );
        for s in [
            br#"{"password":"a","password":"a","confirm_password":"a"}"#.as_slice(),
            br#"{"password":"a","confirm_password":"a","other":true}"#,
            br#"{"password":"a","confirm_password":"b"}"#,
            br#"{"username":"admin","password":"a","confirm_password":"a"}"#,
        ] {
            assert!(NewCredentials::decode(s, false).is_err());
        }
        assert!(NewCredentials::decode(&vec![b' '; MAX_INPUT + 1], false).is_err());
    }
    #[test]
    fn replacement_preserves_principal_and_identity_and_verifies_new_secret() {
        let a = Record::create("fixture-instance", " admin ".into(), &pw("first")).unwrap();
        let encoded = a.encode().unwrap();
        let loaded = Record::decode(&encoded, "fixture-instance").unwrap();
        assert!(Record::decode(&encoded, "foreign").is_err());
        let b = loaded.replace_password(&pw("second")).unwrap();
        assert_eq!(a.account_id, b.account_id);
        assert_eq!(a.username, b.username);
        assert_eq!(b.revision, 2);
        assert!(b.verifier.verify(&pw("second")).unwrap());
        assert!(!b.verifier.verify(&pw("first")).unwrap());
        let status = b.status().to_string();
        assert!(
            !status.contains("argon2")
                && !status.contains("verifier")
                && !status.contains("account_id")
        );
    }
    #[test]
    fn malformed_record_revision_and_duplicate_fields_refuse() {
        let a = Record::create("fixture", "admin".into(), &pw("fixture")).unwrap();
        let text = String::from_utf8(a.encode().unwrap().to_vec()).unwrap();
        for bad in [
            text.replace("\"version\":1", "\"version\":2"),
            text.replace("\"revision\":1", "\"revision\":0"),
            text.replace("\"revision\":1", "\"revision\":1,\"revision\":2"),
            text.replace("\"revision\":1", "\"extra\":false,\"revision\":1"),
        ] {
            assert!(Record::decode(bad.as_bytes(), "fixture").is_err());
        }
        let max = text.replace("\"revision\":1", "\"revision\":18446744073709551615");
        let a = Record::decode(max.as_bytes(), "fixture").unwrap();
        assert!(a.replace_password(&pw("replacement")).is_err());
    }
}
