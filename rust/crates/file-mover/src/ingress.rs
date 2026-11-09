//! Protected HTTP transports; TLS/proxy configuration is a separate boundary.
use crate::{Config, http};
use serde::{Deserialize, Serialize};
use std::{io, path::Path, sync::Arc, task::Poll};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpStream, UnixListener, UnixStream},
};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ProtectedIngress {
    pub producer_socket: String,
    pub operator_socket: String,
    pub proxy_uid: u32,
    pub proxy_gid: u32,
}
impl ProtectedIngress {
    pub(crate) fn validate_payload_root(&self, root: &str) -> Result<(), &'static str> {
        let root = Path::new(root);
        for socket in [&self.producer_socket, &self.operator_socket] {
            let parent = Path::new(socket)
                .parent()
                .ok_or("ingress parent required")?;
            if parent.starts_with(root) || root.starts_with(parent) {
                return Err("ingress endpoint overlaps retained payload scope");
            }
        }
        Ok(())
    }
    pub(crate) fn validate(&self, c: &Config) -> Result<(), &'static str> {
        let uid = mover_fs::ingress::local_user_ids().0;
        if uid == 0
            || self.proxy_uid == 0
            || self.proxy_uid == uid
            || self.proxy_uid == u32::MAX
            || self.proxy_gid == 0
            || self.proxy_gid == u32::MAX
            || ![&self.producer_socket, &self.operator_socket]
                .iter()
                .all(|p| crate::absolute(p) && p.len() <= 107)
        {
            return Err(
                "protected ingress requires bounded canonical socket paths and distinct non-root proxy UID/GID",
            );
        }
        let p = Path::new(&self.producer_socket)
            .parent()
            .ok_or("producer parent required")?;
        let o = Path::new(&self.operator_socket)
            .parent()
            .ok_or("operator parent required")?;
        let state = Path::new(&c.state_database)
            .parent()
            .ok_or("state parent required")?;
        let overlaps = |a: &Path, b: &Path| a.starts_with(b) || b.starts_with(a);
        if overlaps(p, o)
            || overlaps(p, state)
            || overlaps(o, state)
            || [&c.source_root, &c.destination_root]
                .iter()
                .any(|r| overlaps(p, Path::new(r)) || overlaps(o, Path::new(r)))
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
            return Err(
                "ingress parents/custody scopes must be separate; configured generator must match producer syntax",
            );
        }
        Ok(())
    }
}

#[derive(Clone, Copy)]
pub(crate) enum Audience {
    Prototype,
    Producer(bool),
    Native(bool),
    Operator(bool),
}
impl Audience {
    pub(crate) fn authorized(self) -> bool {
        match self {
            Self::Prototype => true,
            Self::Producer(ok) | Self::Native(ok) | Self::Operator(ok) => ok,
        }
    }
    pub(crate) fn producer(self) -> bool {
        matches!(self, Self::Producer(_) | Self::Native(_))
    }
    pub(crate) fn denial(self, r: &http::Request, c: &Config) -> Option<crate::Response> {
        let deny = |status, code| Some(crate::error(status, code, false, None));
        match self {
            Self::Native(_) => {
                if r.head.headers.contains_key("x-file-mover-generator")
                    || r.head.headers.contains_key("cookie")
                    || r.head.headers.keys().any(|h| {
                        h.starts_with("x-forwarded-")
                            || h == "forwarded"
                            || h.starts_with("x-ssl-")
                            || h.starts_with("x-client-")
                    })
                {
                    return deny(400, "unsupported_headers");
                }
                if let Some(crate::native::NativeIngress::Https { authority, .. }) =
                    &c.native_ingress
                    && r.head.headers.get("host").map(Vec::as_slice) != Some(authority.as_bytes())
                {
                    return deny(400, "unsupported_headers");
                }
                if r.head.target != b"/api/v2/jobs" {
                    return deny(403, "producer_route_forbidden");
                }
            }
            Self::Producer(_) => {
                if r.head
                    .headers
                    .get("x-file-mover-generator")
                    .map(Vec::as_slice)
                    != Some(c.generator_id.as_bytes())
                {
                    return deny(403, "caller_not_authorized");
                }
                if r.head.headers.contains_key("cookie")
                    || r.head.headers.get("host").map(Vec::as_slice) != Some(b"localhost")
                {
                    return deny(400, "unsupported_headers");
                }
                if r.head.target != b"/api/v2/jobs" {
                    return deny(403, "producer_route_forbidden");
                }
            }
            Self::Operator(_) if r.head.target == b"/api/v2/jobs" => return deny(404, "not_found"),
            _ => (),
        }
        if !self.producer() && r.head.headers.contains_key("x-file-mover-generator") {
            return deny(400, "unsupported_headers");
        }
        None
    }
}

pub(crate) enum Stream {
    Tcp(TcpStream),
    Unix(UnixStream),
    Tls(Box<tokio_rustls::server::TlsStream<TcpStream>>),
}
impl Stream {
    pub(crate) async fn read(&mut self, bytes: &mut [u8]) -> io::Result<usize> {
        match self {
            Self::Tcp(s) => s.read(bytes).await,
            Self::Unix(s) => s.read(bytes).await,
            Self::Tls(s) => s.read(bytes).await,
        }
    }
    pub(crate) async fn write_all(&mut self, bytes: &[u8]) -> io::Result<()> {
        match self {
            Self::Tcp(s) => s.write_all(bytes).await,
            Self::Unix(s) => s.write_all(bytes).await,
            Self::Tls(s) => s.write_all(bytes).await,
        }
    }
    pub(crate) async fn flush(&mut self) -> io::Result<()> {
        match self {
            Self::Tcp(s) => s.flush().await,
            Self::Unix(s) => s.flush().await,
            Self::Tls(s) => s.flush().await,
        }
    }
    pub(crate) async fn shutdown(&mut self) -> io::Result<()> {
        match self {
            Self::Tcp(s) => s.shutdown().await,
            Self::Unix(s) => s.shutdown().await,
            Self::Tls(s) => s.shutdown().await,
        }
    }
}

pub(crate) struct Bound {
    producer: UnixListener,
    operator: UnixListener,
    endpoints: [mover_fs::ingress::LocalSocket; 2],
    proxy_uid: u32,
}
pub(crate) struct Prepared {
    endpoints: [mover_fs::ingress::LocalSocket; 2],
    proxy_uid: u32,
}
pub(crate) struct Planned {
    producer: mover_fs::ingress::SocketPlan,
    operator: mover_fs::ingress::SocketPlan,
    proxy_uid: u32,
}
impl Planned {
    pub(crate) fn prepare(c: &ProtectedIngress) -> Result<Self, Box<dyn std::error::Error>> {
        // Validate BOTH names before creating either endpoint.
        let producer = mover_fs::ingress::SocketPlan::producer(&c.producer_socket, c.proxy_gid)?;
        let operator = mover_fs::ingress::SocketPlan::operator(&c.operator_socket)?;
        Ok(Self {
            producer,
            operator,
            proxy_uid: c.proxy_uid,
        })
    }
    pub(crate) fn bind(self) -> Result<Prepared, Box<dyn std::error::Error>> {
        Ok(Prepared {
            endpoints: [self.producer.bind()?, self.operator.bind()?],
            proxy_uid: self.proxy_uid,
        })
    }
}
impl Prepared {
    pub(crate) fn activate(self) -> Result<Bound, Box<dyn std::error::Error>> {
        Ok(Bound {
            producer: UnixListener::from_std(self.endpoints[0].listener()?)?,
            operator: UnixListener::from_std(self.endpoints[1].listener()?)?,
            endpoints: self.endpoints,
            proxy_uid: self.proxy_uid,
        })
    }
}
impl Bound {
    pub(crate) fn validate(&self) -> Result<(), Box<dyn std::error::Error>> {
        for endpoint in &self.endpoints {
            endpoint.validate()?;
        }
        Ok(())
    }
    pub(crate) async fn accept(&self) -> io::Result<(Stream, Audience)> {
        std::future::poll_fn(|cx| {
            // A producer flood must not starve a ready local operator.
            match self.operator.poll_accept(cx) {
                Poll::Ready(Ok((stream, _))) => {
                    let authorized = stream
                        .peer_cred()
                        .is_ok_and(|p| p.uid() == mover_fs::ingress::local_user_ids().0);
                    return Poll::Ready(Ok((Stream::Unix(stream), Audience::Operator(authorized))));
                }
                Poll::Ready(Err(e)) => return Poll::Ready(Err(e)),
                Poll::Pending => (),
            }
            self.producer.poll_accept(cx).map(|result| {
                result.map(|(stream, _)| {
                    let authorized = stream.peer_cred().is_ok_and(|p| p.uid() == self.proxy_uid);
                    (Stream::Unix(stream), Audience::Producer(authorized))
                })
            })
        })
        .await
    }
}

pub(crate) async fn accept(
    tcp: Option<&TcpListener>,
    unix: Option<&Bound>,
    native: Option<&crate::native::Bound>,
) -> io::Result<(Stream, Audience)> {
    if let Some(native) = native {
        native.accept().await
    } else if let Some(tcp) = tcp {
        let (s, _) = tcp.accept().await?;
        Ok((Stream::Tcp(s), Audience::Prototype))
    } else {
        unix.expect("configured protected listeners").accept().await
    }
}

pub async fn serve_configured(
    c: Config,
    lifecycle: Arc<crate::control::Lifecycle>,
) -> Result<(), Box<dyn std::error::Error>> {
    c.validate()?;
    let tcp = if c.protected_ingress.is_none() && c.native_ingress.is_none() {
        Some(TcpListener::bind(c.bind).await?)
    } else {
        None
    };
    crate::serve_inner(tcp, c, lifecycle).await
}
