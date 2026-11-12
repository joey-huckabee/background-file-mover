//! Explicit native producer transport. Credentials never enter worker assignments.
use crate::{Config, ingress, tls};
use rustls::{
    RootCertStore,
    client::danger::ServerCertVerifier,
    pki_types::{CertificateDer, PrivateKeyDer, ServerName, UnixTime},
    server::ParsedCertificate,
};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeSet, net::IpAddr, path::Path, sync::Arc, task::Poll};
use tokio::net::{TcpListener, UnixListener};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ClientIdentity {
    pub sha256: String,
    pub generator_id: String,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(tag = "transport", rename_all = "lowercase", deny_unknown_fields)]
pub enum NativeIngress {
    Http {
        operator_socket: String,
    },
    Https {
        operator_socket: String,
        authority: String,
        server_certificates: Vec<String>,
        server_key: String,
        server_ca_certificates: Vec<String>,
        client_ca_certificates: Vec<String>,
        clients: Vec<ClientIdentity>,
    },
}

fn overlaps(a: &Path, b: &Path) -> bool {
    a.starts_with(b) || b.starts_with(a)
}

impl NativeIngress {
    pub fn https(&self) -> bool {
        matches!(self, Self::Https { .. })
    }
    pub fn operator_socket(&self) -> &str {
        match self {
            Self::Http { operator_socket }
            | Self::Https {
                operator_socket, ..
            } => operator_socket,
        }
    }
    pub(crate) fn credential_paths(&self) -> Vec<&str> {
        match self {
            Self::Http { .. } => Vec::new(),
            Self::Https {
                server_certificates,
                server_key,
                server_ca_certificates,
                client_ca_certificates,
                ..
            } => server_certificates
                .iter()
                .chain(server_ca_certificates)
                .chain(client_ca_certificates)
                .map(String::as_str)
                .chain(std::iter::once(server_key.as_str()))
                .collect(),
        }
    }
    pub(crate) fn validate_payload_root(&self, root: &str) -> Result<(), &'static str> {
        for path in std::iter::once(self.operator_socket()).chain(self.credential_paths()) {
            let parent = Path::new(path)
                .parent()
                .ok_or("native ingress parent required")?;
            if overlaps(parent, Path::new(root)) {
                return Err("native ingress overlaps payload scope");
            }
        }
        Ok(())
    }
    pub(crate) fn validate(&self, c: &Config) -> Result<(), &'static str> {
        if c.protected_ingress.is_some() || mover_fs::ingress::local_user_ids().0 == 0 {
            return Err("native ingress requires a non-root account and no protected_ingress");
        }
        if !crate::absolute(self.operator_socket()) || self.operator_socket().len() > 107 {
            return Err("canonical bounded native operator socket required");
        }
        let operator = Path::new(self.operator_socket())
            .parent()
            .ok_or("operator parent required")?;
        let state = Path::new(&c.state_database)
            .parent()
            .ok_or("state parent required")?;
        if overlaps(operator, state)
            || !c
                .generator_id
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-'))
            || !c
                .generator_id
                .as_bytes()
                .first()
                .is_some_and(u8::is_ascii_alphanumeric)
        {
            return Err("native ingress scopes/generator invalid");
        }
        self.validate_payload_root(&c.source_root)?;
        self.validate_payload_root(&c.destination_root)?;
        if let Self::Https {
            authority,
            server_certificates,
            server_ca_certificates,
            client_ca_certificates,
            clients,
            ..
        } = self
        {
            let (_, port) = authority_name(authority)?;
            if port != c.bind.port()
                || !(1..=8).contains(&server_certificates.len())
                || !(1..=16).contains(&server_ca_certificates.len())
                || !(1..=16).contains(&client_ca_certificates.len())
                || !(1..=256).contains(&clients.len())
            {
                return Err("native TLS policy exceeds bounds or authority port differs from bind");
            }
            let mut seen = BTreeSet::new();
            for client in clients {
                if client.generator_id != c.generator_id
                    || client.sha256.len() != 64
                    || !client
                        .sha256
                        .bytes()
                        .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
                    || !seen.insert(&client.sha256)
                {
                    return Err("native TLS client mapping invalid");
                }
            }
            for path in self.credential_paths() {
                if !crate::absolute(path) || path.len() > 4096 {
                    return Err("canonical bounded credential path required");
                }
                let parent = Path::new(path)
                    .parent()
                    .ok_or("credential parent required")?;
                if overlaps(parent, operator) || overlaps(parent, state) {
                    return Err("credentials must be separate from operator/state directories");
                }
            }
        }
        Ok(())
    }
    /// Synchronous local preflight, called only on the guarded startup supervisor.
    pub(crate) fn load(&self) -> Result<Option<Arc<Policy>>, Box<dyn std::error::Error>> {
        let Self::Https {
            authority,
            server_certificates,
            server_key,
            server_ca_certificates,
            client_ca_certificates,
            clients,
            ..
        } = self
        else {
            return Ok(None);
        };
        let chain = certificates(server_certificates)
            .map_err(|e| context("native_ingress.server_certificates", e))?;
        let server_ca = certificates(server_ca_certificates)
            .map_err(|e| context("native_ingress.server_ca_certificates", e))?;
        let client_ca = certificates(client_ca_certificates)
            .map_err(|e| context("native_ingress.client_ca_certificates", e))?;
        let hashes = |certs: &[CertificateDer<'_>]| {
            certs
                .iter()
                .map(|c| mover_fs::sha256_hex(c.as_ref()))
                .collect::<Vec<_>>()
        };
        let policy_sha256 = mover_fs::sha256_hex(&serde_json::to_vec(
            &serde_json::json!({"configuration":self,"server_chain":hashes(&chain),"server_roots":hashes(&server_ca),"client_roots":hashes(&client_ca)}),
        )?);
        let server_sha256 = mover_fs::sha256_hex(chain[0].as_ref());
        let client_roots = roots(client_ca)?;
        let client_verifier = rustls::server::WebPkiClientVerifier::builder_with_provider(
            Arc::new(client_roots.clone()),
            tls::provider(),
        )
        .build()?;
        let key = private_key(server_key).map_err(|e| context("native_ingress.server_key", e))?;
        verify_server_chain(authority, &chain, server_ca)?;
        let server = tls::proof_server_config(chain, key, client_roots)
            .map_err(|_| "native TLS policy/key refused")?;
        Ok(Some(Arc::new(Policy {
            acceptor: tokio_rustls::TlsAcceptor::from(Arc::new(server)),
            fingerprints: clients.iter().map(|c| c.sha256.clone()).collect(),
            client_verifier,
            server_sha256,
            policy_sha256,
        })))
    }
}

/// Prefix a startup error with the configuration field it came from.
pub(crate) fn context(
    field: &str,
    error: Box<dyn std::error::Error>,
) -> Box<dyn std::error::Error> {
    format!("{field}: {error}").into()
}

/// Bounded DER certificates from guarded credential files.
pub(crate) fn certificates(
    paths: &[String],
) -> Result<Vec<CertificateDer<'static>>, Box<dyn std::error::Error>> {
    paths
        .iter()
        .map(|p| {
            let der = CertificateDer::from(mover_fs::credentials::read(p, 65536, false)?);
            ParsedCertificate::try_from(&der).map_err(|_| "invalid DER certificate")?;
            Ok(der)
        })
        .collect()
}
fn roots(certs: Vec<CertificateDer<'static>>) -> Result<RootCertStore, Box<dyn std::error::Error>> {
    let mut result = RootCertStore::empty();
    for der in certs {
        result.add(der).map_err(|_| "invalid DER trust anchor")?;
    }
    Ok(result)
}
/// Guarded private PKCS8 key. The parser distinguishes PKCS1/SEC1/PKCS8; never
/// relabel other DER as PKCS8.
pub(crate) fn private_key(
    path: &str,
) -> Result<PrivateKeyDer<'static>, Box<dyn std::error::Error>> {
    let bytes = mover_fs::credentials::read(path, 16384, true)?;
    let key = PrivateKeyDer::try_from(bytes).map_err(|_| "invalid DER private key")?;
    if !matches!(key, PrivateKeyDer::Pkcs8(_)) {
        return Err("PKCS8 private key required".into());
    }
    Ok(key)
}
/// Verify the served chain, name, validity and usage against configured roots.
pub(crate) fn verify_server_chain(
    authority: &str,
    chain: &[CertificateDer<'static>],
    server_ca: Vec<CertificateDer<'static>>,
) -> Result<(), Box<dyn std::error::Error>> {
    let (name, _) = authority_name(authority)?;
    let name = ServerName::try_from(name).map_err(|_| "invalid TLS server identity")?;
    let verifier = rustls::client::WebPkiServerVerifier::builder_with_provider(
        Arc::new(roots(server_ca)?),
        tls::provider(),
    )
    .build()?;
    verifier
        .verify_server_cert(&chain[0], &chain[1..], &name, &[], UnixTime::now())
        .map_err(|_| "server certificate chain/name/validity/usage refused")?;
    Ok(())
}

/// An exact configured HTTP authority, with explicit canonical port.
pub(crate) fn authority_name(authority: &str) -> Result<(String, u16), &'static str> {
    if authority.len() > 259 || !authority.is_ascii() {
        return Err("bounded ASCII TLS authority required");
    }
    let (host, port) = authority
        .rsplit_once(':')
        .ok_or("TLS authority requires host:port")?;
    let port: u16 = port
        .parse()
        .ok()
        .filter(|p: &u16| *p > 0 && p.to_string() == port)
        .ok_or("canonical authority port required")?;
    let name = if host.starts_with('[') && host.ends_with(']') {
        let ip: std::net::Ipv6Addr = host[1..host.len() - 1]
            .parse()
            .map_err(|_| "invalid authority IPv6")?;
        if format!("[{ip}]") != host {
            return Err("canonical authority IPv6 required");
        }
        ip.to_string()
    } else {
        if host.is_empty()
            || host.ends_with('.')
            || host != host.to_ascii_lowercase()
            || host.contains(':')
        {
            return Err("canonical authority host required");
        }
        if let Ok(ip) = host.parse::<IpAddr>()
            && ip.to_string() != host
        {
            return Err("canonical authority IP required");
        }
        ServerName::try_from(host.to_owned()).map_err(|_| "invalid authority host")?;
        host.to_owned()
    };
    Ok((name, port))
}

pub(crate) struct Policy {
    acceptor: tokio_rustls::TlsAcceptor,
    pub(crate) fingerprints: BTreeSet<String>,
    pub(crate) client_verifier: Arc<dyn rustls::server::danger::ClientCertVerifier>,
    pub(crate) server_sha256: String,
    pub(crate) policy_sha256: String,
}
impl Policy {
    pub(crate) async fn accept(
        &self,
        stream: ingress::Stream,
        deadline: tokio::time::Instant,
    ) -> Option<(
        ingress::Stream,
        ingress::Audience,
        Vec<CertificateDer<'static>>,
    )> {
        let ingress::Stream::Tcp(stream) = stream else {
            return None;
        };
        // timeout_at may poll its inner future before recognizing expiration.
        if tokio::time::Instant::now() >= deadline {
            return None;
        }
        let accept = self.acceptor.accept_with(stream, |connection| {
            // Send buffering only; receive/handshake bounds are separate Rustls limits.
            connection.set_buffer_limit(Some(65536));
        });
        let stream = tokio::time::timeout_at(deadline, accept).await.ok()?.ok()?;
        if tokio::time::Instant::now() >= deadline {
            return None;
        }
        if stream.get_ref().1.alpn_protocol() != Some(b"http/1.1") {
            return None;
        }
        let leaf = stream.get_ref().1.peer_certificates()?.first()?;
        let approved = self
            .fingerprints
            .contains(&mover_fs::sha256_hex(leaf.as_ref()));
        let peer = stream
            .get_ref()
            .1
            .peer_certificates()?
            .iter()
            .map(|c| c.clone().into_owned())
            .collect();
        Some((
            ingress::Stream::Tls(Box::new(stream)),
            ingress::Audience::Native(approved),
            peer,
        ))
    }
}

pub(crate) struct Prepared {
    operator: mover_fs::ingress::LocalSocket,
    listener: std::net::TcpListener,
    pub(crate) policy: Option<Arc<Policy>>,
    reload_plan: Option<mover_fs::ingress::SocketPlan>,
}
pub(crate) struct Bound {
    operator_socket: mover_fs::ingress::LocalSocket,
    operator: UnixListener,
    listener: TcpListener,
    pub(crate) manager: Option<Arc<crate::reload::Manager>>,
    _reload: Option<crate::tls_reload_ipc::Server>,
    /// Alternates admin/producer priority so neither flood starves the other.
    admin_first: std::sync::atomic::AtomicBool,
}
impl Prepared {
    pub(crate) fn bind(
        c: &Config,
        operator: mover_fs::ingress::SocketPlan,
        policy: Option<Arc<Policy>>,
        reload_plan: Option<mover_fs::ingress::SocketPlan>,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        let listener = std::net::TcpListener::bind(c.bind)?;
        listener.set_nonblocking(true)?;
        Ok(Self {
            operator: operator.bind()?,
            listener,
            policy,
            reload_plan,
        })
    }
    pub(crate) fn activate(
        self,
        c: &Config,
        lifecycle: Arc<crate::control::Lifecycle>,
        guard: Arc<mover_fs::InstanceGuard>,
    ) -> Result<Bound, Box<dyn std::error::Error>> {
        let manager = self
            .policy
            .map(|p| crate::reload::Manager::new(c.clone(), p, lifecycle.clone(), guard.clone()));
        let reload = match (self.reload_plan, manager.as_ref()) {
            (Some(plan), Some(manager)) => Some(crate::tls_reload_ipc::Server::start(
                plan,
                guard,
                lifecycle.stop.clone(),
                manager.clone(),
            )?),
            (None, None) => None,
            _ => return Err("TLS reload startup mismatch".into()),
        };
        Ok(Bound {
            operator: UnixListener::from_std(self.operator.listener()?)?,
            operator_socket: self.operator,
            listener: TcpListener::from_std(self.listener)?,
            manager,
            _reload: reload,
            admin_first: std::sync::atomic::AtomicBool::new(false),
        })
    }
}
impl Bound {
    pub(crate) fn validate(&self) -> Result<(), Box<dyn std::error::Error>> {
        Ok(self.operator_socket.validate()?)
    }
    pub(crate) fn address(&self) -> std::io::Result<std::net::SocketAddr> {
        self.listener.local_addr()
    }
    /// Poll order: private operator first; then admin and producer alternate
    /// priority after each accept, so a flood on either TCP listener cannot
    /// starve the other. Excess connections are still accepted and refused promptly.
    pub(crate) async fn accept(
        &self,
        admin: Option<&TcpListener>,
    ) -> std::io::Result<(ingress::Stream, ingress::Audience)> {
        use std::sync::atomic::Ordering::Relaxed;
        std::future::poll_fn(|cx| {
            match self.operator.poll_accept(cx) {
                Poll::Ready(Ok((s, _))) => {
                    let ok = s
                        .peer_cred()
                        .is_ok_and(|p| p.uid() == mover_fs::ingress::local_user_ids().0);
                    return Poll::Ready(Ok((
                        ingress::Stream::Unix(s),
                        ingress::Audience::Operator(ok),
                    )));
                }
                Poll::Ready(Err(e)) => return Poll::Ready(Err(e)),
                Poll::Pending => (),
            }
            let poll_admin = |cx: &mut std::task::Context<'_>| {
                admin.map(|a| {
                    a.poll_accept(cx).map(|r| {
                        r.map(|(s, _)| (ingress::Stream::Tcp(s), ingress::Audience::Admin))
                    })
                })
            };
            let poll_producer = |cx: &mut std::task::Context<'_>| {
                self.listener.poll_accept(cx).map(|r| {
                    r.map(|(s, _)| (ingress::Stream::Tcp(s), ingress::Audience::Native(true)))
                })
            };
            let admin_first = self.admin_first.load(Relaxed);
            for turn in [admin_first, !admin_first] {
                let ready = if turn {
                    poll_admin(cx).unwrap_or(Poll::Pending)
                } else {
                    poll_producer(cx)
                };
                if let Poll::Ready(result) = ready {
                    // Whoever was just served yields priority to the other.
                    self.admin_first.store(!turn, Relaxed);
                    return Poll::Ready(result);
                }
            }
            Poll::Pending
        })
        .await
    }
}
