//! Native TLS dependency/target proof. No REST listener or credential file loading.
use rustls::{
    RootCertStore, ServerConfig,
    crypto::CryptoProvider,
    pki_types::{CertificateDer, PrivateKeyDer},
    server::{NoServerSessionStorage, WebPkiClientVerifier},
};
use std::{error::Error, sync::Arc};

/// Select one reviewed provider explicitly, independent of process-global defaults.
pub fn provider() -> Arc<CryptoProvider> {
    Arc::new(rustls::crypto::aws_lc_rs::default_provider())
}

/// Exercise native provider initialization and OS entropy in the shipped binary.
pub fn check_platform() -> Result<(), Box<dyn Error>> {
    provider()
        .secure_random
        .fill(&mut [0_u8; 32])
        .map_err(|_| "TLS provider could not obtain secure randomness")?;
    Ok(())
}

/// Construct the dependency proof's mandatory-client-certificate server policy.
///
/// CA validation is not application authorization: the later REST integration
/// must also bind the verified leaf to its approved generator before admission.
/// Inputs are owned DER bytes; this helper does not read files or open sockets.
pub fn proof_server_config(
    certificates: Vec<CertificateDer<'static>>,
    private_key: PrivateKeyDer<'static>,
    client_roots: RootCertStore,
) -> Result<ServerConfig, Box<dyn Error>> {
    let crypto = provider();
    let verifier =
        WebPkiClientVerifier::builder_with_provider(Arc::new(client_roots), Arc::clone(&crypto))
            .build()?;
    let mut config = ServerConfig::builder_with_provider(crypto)
        .with_protocol_versions(&[&rustls::version::TLS13, &rustls::version::TLS12])?
        .with_client_cert_verifier(verifier)
        .with_single_cert(certificates, private_key)?;
    config.alpn_protocols = vec![b"http/1.1".to_vec()];
    config.max_early_data_size = 0;
    config.session_storage = Arc::new(NoServerSessionStorage {});
    config.send_tls13_tickets = 0;
    Ok(config)
}
