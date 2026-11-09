//! Actual SLES-target TLS handshakes, using ephemeral gate-generated credentials.
//! This is not a REST endpoint or certificate-to-generator authorization test.
use file_mover::tls;
use rustls::{
    ClientConfig, ProtocolVersion, RootCertStore, SupportedProtocolVersion,
    client::Resumption,
    pki_types::{CertificateDer, PrivateKeyDer, PrivatePkcs8KeyDer, ServerName},
};
use std::{fs, path::PathBuf, sync::Arc, time::Duration};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpStream},
    time::timeout,
};
use tokio_rustls::{TlsAcceptor, TlsConnector};

const MESSAGE: &[u8] = b"SLES12SP5 native TLS dependency proof";
const DEADLINE: Duration = Duration::from_secs(5);

fn fixture(name: &str) -> Vec<u8> {
    let directory = std::env::var_os("FILE_MOVER_TLS_FIXTURES")
        .expect("run through check-rust-sles.py: gate-generated TLS fixtures required");
    fs::read(PathBuf::from(directory).join(name)).expect("read gate-generated TLS fixture")
}

fn certificate(name: &str) -> CertificateDer<'static> {
    CertificateDer::from(fixture(name))
}

fn key(name: &str) -> PrivateKeyDer<'static> {
    PrivatePkcs8KeyDer::from(fixture(name)).into()
}

fn roots(name: &str) -> RootCertStore {
    let mut roots = RootCertStore::empty();
    roots.add(certificate(name)).expect("valid fixture CA");
    roots
}

#[derive(Debug)]
struct Proof {
    version: ProtocolVersion,
    peer: Vec<u8>,
}

struct Case {
    version: &'static SupportedProtocolVersion,
    server: &'static str,
    client: Option<&'static str>,
    server_ca: &'static str,
    server_name: &'static str,
}

impl Case {
    fn valid(version: &'static SupportedProtocolVersion) -> Self {
        Self {
            version,
            server: "server",
            client: Some("client"),
            server_ca: "ca.der",
            server_name: "localhost",
        }
    }
}

fn handshake(case: Case) -> (Result<Proof, String>, Result<Proof, String>) {
    let server = tls::proof_server_config(
        vec![certificate(&format!("{}.der", case.server))],
        key(&format!("{}.key.der", case.server)),
        roots("ca.der"),
    )
    .expect("construct proof server policy");
    assert_eq!(server.max_early_data_size, 0);
    assert_eq!(server.send_tls13_tickets, 0);
    assert!(!server.session_storage.can_cache());
    let client = ClientConfig::builder_with_provider(tls::provider())
        .with_protocol_versions(&[case.version])
        .expect("selected protocol")
        .with_root_certificates(roots(case.server_ca));
    let mut client = match case.client {
        Some(name) => client
            .with_client_auth_cert(
                vec![certificate(&format!("{name}.der"))],
                key(&format!("{name}.key.der")),
            )
            .expect("construct proof client credentials"),
        None => client.with_no_client_auth(),
    };
    client.resumption = Resumption::disabled();
    client.alpn_protocols = vec![b"http/1.1".to_vec()];
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    runtime.block_on(async move {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server_task = tokio::spawn(async move {
            timeout(DEADLINE, async move {
                let (socket, _) = listener.accept().await.map_err(|e| e.to_string())?;
                let mut stream = TlsAcceptor::from(Arc::new(server))
                    .accept(socket)
                    .await
                    .map_err(|e| format!("TLS accept: {e}"))?;
                let connection = stream.get_ref().1;
                let proof = Proof {
                    version: connection
                        .protocol_version()
                        .ok_or("missing server version")?,
                    peer: connection
                        .peer_certificates()
                        .and_then(|c| c.first())
                        .ok_or("missing authenticated client")?
                        .as_ref()
                        .to_vec(),
                };
                if connection.alpn_protocol() != Some(b"http/1.1") {
                    return Err("wrong server ALPN".into());
                }
                let mut input = vec![0; MESSAGE.len()];
                stream
                    .read_exact(&mut input)
                    .await
                    .map_err(|e| e.to_string())?;
                if input != MESSAGE {
                    return Err("TLS payload differs".into());
                }
                stream.write_all(&input).await.map_err(|e| e.to_string())?;
                stream.flush().await.map_err(|e| e.to_string())?;
                stream.shutdown().await.map_err(|e| e.to_string())?;
                Ok::<_, String>(proof)
            })
            .await
            .expect("server deadline is not certificate-refusal evidence")
        });
        let client_result = timeout(DEADLINE, async move {
            let socket = TcpStream::connect(address)
                .await
                .map_err(|e| e.to_string())?;
            let mut stream = TlsConnector::from(Arc::new(client))
                .connect(ServerName::try_from(case.server_name).unwrap(), socket)
                .await
                .map_err(|e| format!("TLS connect: {e}"))?;
            let connection = stream.get_ref().1;
            let proof = Proof {
                version: connection
                    .protocol_version()
                    .ok_or("missing client version")?,
                peer: connection
                    .peer_certificates()
                    .and_then(|c| c.first())
                    .ok_or("missing authenticated server")?
                    .as_ref()
                    .to_vec(),
            };
            if connection.alpn_protocol() != Some(b"http/1.1") {
                return Err("wrong client ALPN".into());
            }
            stream.write_all(MESSAGE).await.map_err(|e| e.to_string())?;
            stream.flush().await.map_err(|e| e.to_string())?;
            let mut response = vec![0; MESSAGE.len()];
            stream
                .read_exact(&mut response)
                .await
                .map_err(|e| e.to_string())?;
            if response != MESSAGE {
                return Err("TLS reply differs".into());
            }
            Ok::<_, String>(proof)
        })
        .await
        .expect("client deadline is not certificate-refusal evidence");
        let server_result = timeout(DEADLINE, server_task)
            .await
            .expect("server task finishes")
            .expect("server task does not panic");
        (client_result, server_result)
    })
}

#[test]
fn native_tls12_and_tls13_authenticate_both_peers_and_exchange_bytes() {
    tls::check_platform().unwrap();
    for (version, expected) in [
        (&rustls::version::TLS12, ProtocolVersion::TLSv1_2),
        (&rustls::version::TLS13, ProtocolVersion::TLSv1_3),
    ] {
        let (client, server) = handshake(Case::valid(version));
        let client = client.expect("authenticated encrypted reply");
        let server = server.expect("authenticated encrypted request");
        assert_eq!(client.version, expected);
        assert_eq!(server.version, expected);
        assert_eq!(client.peer, fixture("server.der"));
        assert_eq!(server.peer, fixture("client.der"));
    }
}

#[test]
fn missing_untrusted_expired_and_wrong_usage_clients_cannot_exchange_application_data() {
    for version in [&rustls::version::TLS12, &rustls::version::TLS13] {
        for client in [
            None,
            Some("untrusted-client"),
            Some("expired-client"),
            Some("wrong-usage-client"),
        ] {
            let (client_result, server_result) = handshake(Case {
                client,
                ..Case::valid(version)
            });
            assert!(
                client_result.is_err(),
                "invalid client exchanged bytes: {client:?}"
            );
            assert!(
                server_result
                    .as_ref()
                    .is_err_and(|e| e.starts_with("TLS accept:")),
                "server did not reject the client during TLS: {client:?}: {server_result:?}"
            );
        }
    }
}

#[test]
fn wrong_server_name_untrusted_server_and_expired_server_cannot_exchange_application_data() {
    for version in [&rustls::version::TLS12, &rustls::version::TLS13] {
        for case in [
            Case {
                server_name: "wrong.example.invalid",
                ..Case::valid(version)
            },
            Case {
                server_ca: "other-ca.der",
                ..Case::valid(version)
            },
            Case {
                server: "expired-server",
                ..Case::valid(version)
            },
        ] {
            let (client, server) = handshake(case);
            assert!(
                client
                    .as_ref()
                    .is_err_and(|e| e.starts_with("TLS connect:")),
                "client did not reject server during TLS: {client:?}"
            );
            assert!(server.is_err(), "invalid server exchanged application data");
        }
    }
}

#[test]
fn malformed_empty_mismatched_credentials_and_empty_trust_refuse_policy_construction() {
    assert!(tls::proof_server_config(vec![], key("server.key.der"), roots("ca.der")).is_err());
    assert!(
        tls::proof_server_config(
            vec![CertificateDer::from(vec![0, 1, 2])],
            key("server.key.der"),
            roots("ca.der")
        )
        .is_err()
    );
    assert!(
        tls::proof_server_config(
            vec![certificate("server.der")],
            key("client.key.der"),
            roots("ca.der")
        )
        .is_err()
    );
    assert!(
        tls::proof_server_config(
            vec![certificate("server.der")],
            key("server.key.der"),
            RootCertStore::empty()
        )
        .is_err()
    );
}
