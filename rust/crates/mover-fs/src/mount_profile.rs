//! Local proc observations supplement, never replace, descriptor/enrollment custody.
use super::{ClaimError, Result};
use rustix::fd::{AsRawFd, OwnedFd};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, io::Read, path::Path};

const LIMIT: u64 = 1024 * 1024;
fn blocked(reason: &'static str) -> ClaimError {
    ClaimError::Blocked(reason)
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum MountProfile {
    #[serde(rename = "NMP-41B")]
    Buffered,
    #[serde(rename = "NMP-41N")]
    NoacDiagnostic,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NfsMountProfile {
    pub profile: MountProfile,
    pub mountpoint: String,
    pub source: String,
    pub addr: String,
}

fn canonical(value: &str) -> bool {
    value.starts_with('/')
        && !value.chars().any(char::is_control)
        && !value.contains('\\')
        && (value == "/" || value[1..].split('/').all(|p| !["", ".", ".."].contains(&p)))
}
impl NfsMountProfile {
    pub fn validate(&self) -> Result<()> {
        if !canonical(&self.mountpoint)
            || self.mountpoint.len() > 1024
            || self.source.is_empty()
            || self.source.len() > 512
            || self.source.chars().any(char::is_control)
            || self.addr.parse::<std::net::IpAddr>().is_err()
        {
            return Err(blocked("invalid NFS mount declaration"));
        }
        Ok(())
    }
    pub(crate) fn observe(&self, path: &str) -> Result<MountObservation> {
        self.validate()?;
        if !super::nfs_qualification_enabled() {
            return Err(blocked("production NFS disabled"));
        }
        let namespace = std::fs::read_link("/proc/self/ns/mnt")
            .map_err(|_| blocked("mount namespace observation unavailable"))?;
        let inventory = local_text("/proc/self/mountinfo", LIMIT)?;
        let record = select(&inventory, path, self)?;
        Ok(MountObservation {
            pin: format!(
                "{:x}",
                Sha256::digest(
                    serde_json::to_vec(&(path, self, namespace.to_str(), &record))
                        .map_err(|_| blocked("mount observation serialization"))?
                )
            ),
            mount_id: record.id,
        })
    }
}

#[derive(PartialEq, Eq)]
pub(crate) struct MountObservation {
    pub pin: String,
    mount_id: u64,
}
impl MountObservation {
    pub fn validate_descriptor(&self, fd: &OwnedFd) -> Result<()> {
        let text = local_text(&format!("/proc/self/fdinfo/{}", fd.as_raw_fd()), 16384)?;
        let ids = text
            .lines()
            .filter_map(|line| line.strip_prefix("mnt_id:"))
            .collect::<Vec<_>>();
        if ids.len() != 1 || ids[0].trim().parse::<u64>().ok() != Some(self.mount_id) {
            return Err(blocked("root descriptor mount differs from inventory"));
        }
        Ok(())
    }
}

fn local_text(path: &str, limit: u64) -> Result<String> {
    let mut bytes = Vec::new();
    std::fs::File::open(path)
        .map_err(|_| blocked("local mount metadata unavailable"))?
        .take(limit + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| blocked("local mount metadata unreadable"))?;
    if bytes.len() as u64 > limit {
        return Err(blocked("local mount metadata too large"));
    }
    String::from_utf8(bytes).map_err(|_| blocked("invalid local mount metadata encoding"))
}

#[derive(Clone, Debug, Serialize)]
struct Record {
    id: u64,
    parent: u64,
    device: String,
    root: String,
    point: String,
    vfs: BTreeMap<String, Option<String>>,
    optional: Vec<String>,
    filesystem: String,
    source: String,
    options: BTreeMap<String, Option<String>>,
}
fn unescape(value: &str) -> Result<String> {
    let bytes = value.as_bytes();
    let mut out = Vec::new();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] != b'\\' {
            out.push(bytes[i]);
            i += 1;
        } else {
            let escape = bytes
                .get(i + 1..i + 4)
                .ok_or(blocked("invalid mount path escape"))?;
            out.push(match escape {
                b"040" => b' ',
                b"011" => b'\t',
                b"012" => b'\n',
                b"134" => b'\\',
                _ => return Err(blocked("invalid mount path escape")),
            });
            i += 4;
        }
    }
    String::from_utf8(out).map_err(|_| blocked("invalid mount path encoding"))
}
fn options(value: &str) -> Result<BTreeMap<String, Option<String>>> {
    let mut out = BTreeMap::new();
    for item in value.split(',') {
        let (key, val) = item
            .split_once('=')
            .map_or((item, None), |(k, v)| (k, Some(v.to_owned())));
        if key.is_empty() || val.as_deref() == Some("") || out.insert(key.into(), val).is_some() {
            return Err(blocked("invalid or duplicate mount option"));
        }
    }
    Ok(out)
}
fn positive(value: &str) -> Result<u64> {
    value
        .parse::<u64>()
        .ok()
        .filter(|n| *n > 0)
        .ok_or(blocked("invalid mount numeric field"))
}
fn parse(text: &str) -> Result<Vec<Record>> {
    if text.len() as u64 > LIMIT {
        return Err(blocked("mount inventory too large"));
    }
    let mut out = BTreeMap::new();
    for line in text.lines() {
        let f = line.split_whitespace().collect::<Vec<_>>();
        let pivot = f
            .iter()
            .position(|v| *v == "-")
            .ok_or(blocked("invalid mount inventory"))?;
        if pivot < 6 || f.len() != pivot + 4 {
            return Err(blocked("invalid mount inventory"));
        }
        let id = positive(f[0])?;
        let (major, minor) = f[2]
            .split_once(':')
            .ok_or(blocked("invalid mount device"))?;
        if major.parse::<u32>().is_err() || minor.parse::<u32>().is_err() {
            return Err(blocked("invalid mount device"));
        }
        let root = unescape(f[3])?;
        let point = unescape(f[4])?;
        // Kernel inventories may contain escaped control/backslash paths elsewhere.
        // They are retained verbatim; configured candidate paths are stricter.
        if !Path::new(&root).is_absolute() || !Path::new(&point).is_absolute() {
            return Err(blocked("invalid mount path"));
        }
        let record = Record {
            id,
            parent: positive(f[1])?,
            device: f[2].into(),
            root,
            point,
            vfs: options(f[5])?,
            optional: f[6..pivot].iter().map(|s| (*s).into()).collect(),
            filesystem: f[pivot + 1].into(),
            source: unescape(f[pivot + 2])?,
            options: options(f[pivot + 3])?,
        };
        if out.insert(id, record).is_some() {
            return Err(blocked("duplicate mount identity"));
        }
    }
    if out.is_empty() {
        return Err(blocked("empty mount inventory"));
    }
    Ok(out.into_values().collect())
}
fn select(text: &str, path: &str, expected: &NfsMountProfile) -> Result<Record> {
    expected.validate()?;
    if !canonical(path) || !Path::new(path).starts_with(&expected.mountpoint) {
        return Err(blocked("root outside declared mountpoint"));
    }
    let records = parse(text)?;
    let covering = records
        .iter()
        .filter(|r| Path::new(path).starts_with(&r.point))
        .collect::<Vec<_>>();
    let mut points = std::collections::BTreeSet::new();
    if covering.iter().any(|r| !points.insert(&r.point)) {
        return Err(blocked("stacked covering mounts"));
    }
    let record = covering
        .into_iter()
        .max_by_key(|r| r.point.len())
        .ok_or(blocked("no covering mount"))?;
    if record.point != expected.mountpoint
        || record.root != "/"
        || !["nfs", "nfs4"].contains(&record.filesystem.as_str())
    {
        return Err(blocked("missing or substituted NFS mount"));
    }
    if record.source != expected.source
        || record.options.get("addr").and_then(|v| v.as_deref()) != Some(expected.addr.as_str())
    {
        return Err(blocked("NFS endpoint/export declaration mismatch"));
    }
    if records
        .iter()
        .any(|r| r.id != record.id && Path::new(&r.point).starts_with(path))
    {
        return Err(blocked("nested mount in approved root"));
    }
    check_options(record, &expected.profile)?;
    Ok(record.clone())
}
fn check_options(r: &Record, profile: &MountProfile) -> Result<()> {
    let o = &r.options;
    let value = |k: &str| o.get(k).and_then(|v| v.as_deref());
    if !r.vfs.contains_key("rw")
        || r.vfs.contains_key("ro")
        || !o.contains_key("rw")
        || o.contains_key("ro")
    {
        return Err(blocked("NFS mount must be writable"));
    }
    if value("vers") != Some("4.1") || value("proto") != Some("tcp") || value("sec") != Some("sys")
    {
        return Err(blocked("NFS version/transport/security outside profile"));
    }
    if !o.contains_key("hard")
        || [
            "soft",
            "softerr",
            "softreval",
            "nocto",
            "nolock",
            "nosharecache",
            "fsc",
        ]
        .iter()
        .any(|k| o.contains_key(*k))
        || value("local_lock").unwrap_or("none") != "none"
        || value("lookupcache").unwrap_or("all") != "all"
        || value("nconnect").unwrap_or("1") != "1"
        || value("port").unwrap_or("2049") != "2049"
    {
        return Err(blocked("NFS retry/coherence/connection outside profile"));
    }
    let flags = [
        "rw",
        "sync",
        "async",
        "hard",
        "noac",
        "ac",
        "cto",
        "nosoftreval",
        "lock",
        "resvport",
        "noresvport",
        "sharecache",
        "nofsc",
    ];
    let values = [
        "vers",
        "rsize",
        "wsize",
        "namlen",
        "acregmin",
        "acregmax",
        "acdirmin",
        "acdirmax",
        "proto",
        "timeo",
        "retrans",
        "sec",
        "clientaddr",
        "local_lock",
        "addr",
        "port",
        "lookupcache",
        "nconnect",
        "fatal_neterrors",
    ];
    for (k, v) in o {
        if !(flags.contains(&k.as_str()) && v.is_none()
            || values.contains(&k.as_str()) && v.is_some())
        {
            return Err(blocked("unreviewed or malformed NFS mount option"));
        }
    }
    for k in ["rsize", "wsize", "namlen", "timeo", "retrans"] {
        positive(value(k).ok_or(blocked("missing effective NFS option"))?)?;
    }
    if o.contains_key("sync") && o.contains_key("async")
        || o.contains_key("ac") && o.contains_key("noac")
    {
        return Err(blocked("conflicting NFS cache/write policy"));
    }
    if match profile {
        MountProfile::Buffered => o.contains_key("sync") || o.contains_key("noac"),
        MountProfile::NoacDiagnostic => !o.contains_key("sync") || !o.contains_key("noac"),
    } {
        return Err(blocked("NFS cache/write profile mismatch"));
    }
    Ok(())
}

pub(crate) fn declaration(
    filesystem: &super::SourceFilesystem,
    profile: Option<&NfsMountProfile>,
) -> Result<()> {
    match (filesystem, profile) {
        (super::SourceFilesystem::Local, None) => Ok(()),
        (super::SourceFilesystem::Nfs, Some(p)) => p.validate(),
        _ => Err(blocked(
            "explicit NFS profile required only for NFS bindings",
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn declaration() -> NfsMountProfile {
        NfsMountProfile {
            profile: MountProfile::Buffered,
            mountpoint: "/share".into(),
            source: "192.0.2.1:/export".into(),
            addr: "192.0.2.1".into(),
        }
    }
    fn inventory() -> String {
        "1 2 0:1 / / rw - overlay overlay rw\n4 1 0:9 / /share rw,relatime shared:8 - nfs4 192.0.2.1:/export rw,vers=4.1,rsize=1048576,wsize=1048576,namlen=255,hard,proto=tcp,timeo=600,retrans=2,sec=sys,addr=192.0.2.1,local_lock=none\n".into()
    }
    #[test]
    fn profile_defaults_and_diagnostic_writes_are_distinct() {
        let d = declaration();
        let b = inventory();
        assert_eq!(select(&b, "/share/source", &d).unwrap().id, 4);
        let n = b.replace("rw,vers", "rw,sync,noac,vers");
        assert!(select(&n, "/share/source", &d).is_err());
        let mut d = d;
        d.profile = MountProfile::NoacDiagnostic;
        assert!(select(&n, "/share/source", &d).is_ok());
        assert!(select(&b, "/share/source", &d).is_err());
    }
    #[test]
    fn retry_security_and_unknown_option_changes_refuse() {
        let text = inventory();
        for (old, new) in [
            ("hard,", "soft,"),
            ("hard,", "hard,softreval,"),
            ("hard,", "hard,nocto,"),
            ("vers=4.1", "vers=3"),
            ("vers=4.1", "vers=4.2"),
            ("proto=tcp", "proto=udp"),
            ("sec=sys", "sec=krb5p"),
            ("local_lock=none", "local_lock=all"),
            ("hard,", "hard,nconnect=2,"),
            ("hard,", "hard,lookupcache=none,"),
            ("hard,", "hard,unknown=1,"),
            ("hard,", "hard,hard,"),
            ("rw,relatime", "ro,relatime"),
            ("timeo=600", "timeo=0"),
        ] {
            assert!(
                select(&text.replace(old, new), "/share/source", &declaration()).is_err(),
                "{new}"
            );
        }
    }
    #[test]
    fn missing_nested_stacked_and_subtree_mounts_refuse() {
        let text = inventory();
        assert!(
            select(
                text.lines().next().unwrap(),
                "/share/source",
                &declaration()
            )
            .is_err()
        );
        assert!(select(&text, "/shareholder/source", &declaration()).is_err());
        assert!(select(&text, "/share/../source", &declaration()).is_err());
        for row in [
            "5 4 0:2 / /share/source/nested rw - tmpfs tmpfs rw\n",
            "5 1 0:9 / /share rw - nfs4 host:/ rw\n",
        ] {
            assert!(select(&(text.clone() + row), "/share/source", &declaration()).is_err());
        }
        assert!(
            select(
                &text.replace("0:9 / /share", "0:9 /alias /share"),
                "/share/source",
                &declaration()
            )
            .is_err()
        );
        let mut d = declaration();
        d.addr = "192.0.2.2".into();
        assert!(select(&text, "/share/source", &d).is_err());
    }
    #[test]
    fn inventory_parser_is_bounded_and_preserves_kernel_fields() {
        let text = inventory();
        let escaped = text.replace("/share", r"/a\040b\134c\011d\012e");
        let r = parse(&escaped).unwrap();
        assert_eq!(r[1].point, "/a b\\c\td\ne");
        assert_eq!(r[1].optional, ["shared:8"]);
        for text in [
            "".into(),
            "invalid".into(),
            text.clone() + &text,
            text.replace("/share", r"/bad\099"),
            "x".repeat(LIMIT as usize + 1),
        ] {
            assert!(parse(&text).is_err());
        }
    }
    #[test]
    fn declarations_cannot_be_silently_added_downgraded_or_malformed() {
        use super::super::SourceFilesystem::{Local, Nfs};
        let d = declaration();
        assert!(super::declaration(&Local, None).is_ok());
        assert!(super::declaration(&Nfs, Some(&d)).is_ok());
        assert!(super::declaration(&Nfs, None).is_err());
        assert!(super::declaration(&Local, Some(&d)).is_err());
        for field in ["profile", "addr", "mountpoint"] {
            let mut value = serde_json::to_value(&d).unwrap();
            value[field] = serde_json::json!("invalid");
            assert!(
                serde_json::from_value::<NfsMountProfile>(value)
                    .map_or(true, |d| d.validate().is_err())
            );
        }
    }
    #[test]
    fn descriptor_must_belong_to_selected_mount() {
        let fd = rustix::fs::open(
            "/",
            rustix::fs::OFlags::RDONLY | rustix::fs::OFlags::DIRECTORY,
            rustix::fs::Mode::empty(),
        )
        .unwrap();
        assert!(
            MountObservation {
                pin: String::new(),
                mount_id: 0
            }
            .validate_descriptor(&fd)
            .is_err()
        );
    }
}
