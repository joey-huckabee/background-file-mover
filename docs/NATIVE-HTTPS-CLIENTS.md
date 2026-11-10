# Using independent HTTPS producer clients

The SLES server runs the Rust file-mover executable. These commands run on the
producer/client machine. [Increment126](RUST-INCREMENT-126.md) records the exact
tested client image, versions, binary hashes, results and qualification limits.
The test client uses curl 7.88.1 with OpenSSL 3.0.22 and the OpenSSL 3.0.22 CLI.
This does not require installing a compiler, curl or a newer system OpenSSL on
the SLES server. Older clients and other TLS backends need their own checks.

Complete the [server setup](NATIVE-HTTPS-SETUP.md) first. The approved client
leaf fingerprint must map to the configured generator. The request's generator
must agree, and its source directory must be inside that generator's configured
source root on the server. Producer HTTPS exposes the submission route; operator
and reload commands use their existing private host-local interfaces.

## Prepare client credentials

Use your approved CA-issued client certificate/key and the server's trust root.
The following converts DER files to PEM on the client machine; it does not change
the DER/PKCS8 files used by the server. Work in a private client-owned directory:

```sh
umask 077
openssl x509 -inform DER -in approved-client.der -out approved-client.pem
openssl pkey -inform DER -in approved-client.key.der -out approved-client.key.pem
openssl x509 -inform DER -in server-root.der -out server-root.pem
chmod 600 approved-client.key.pem
```

The URL hostname must match the server certificate and configured `authority`.
Keep clocks correct for certificate validity. Do not use `--insecure` or disable
hostname/chain checks to work around a setup failure.

## Submit with curl

Prepare `submission.json` using the [producer contract](api/PRODUCER-MANIFEST-CONTRACT.md).
Retain its UUID and immutable assertions for every transport retry. Then use
the actual configured authority in the URL:

```sh
curl --disable --silent --show-error --http1.1 \
  --proto '=https' --noproxy '*' \
  --cacert server-root.pem \
  --cert approved-client.pem --key approved-client.key.pem \
  --tlsv1.3 --tls-max 1.3 \
  --connect-timeout 3 --max-time 10 --retry 0 \
  --header 'Content-Type: application/json' \
  --data-binary @submission.json \
  --write-out '\nHTTP %{http_code}\n' \
  https://mover.example.internal:8443/api/v2/jobs
```

For an exact TLS1.2 check, replace `--tlsv1.3 --tls-max 1.3` with
`--tlsv1.2 --tls-max 1.2`. Use separate `--proto` and `'=https'` arguments;
the tested curl 7.88.1 rejects the `--proto=https` spelling.
`--disable` comes first so an existing `.curlrc` cannot alter verification,
logging or retries. These commands connect directly, without a proxy.

For a controlled address-resolution diagnostic, add
`--resolve 'mover.example.internal:8443:192.0.2.10'`, substituting the actual
server address. Keep the original URL hostname: this preserves both certificate
verification and the configured HTTP `Host` authority.

Check both curl's exit status and the HTTP status/JSON. Curl can exit 0 for an
HTTP403. A valid whole-set receipt is HTTP202 with `source_paths_released:true`;
this acknowledges custody, while delivery progress remains a separate operator
observation. A timeout or lost reply does not establish whether admission
occurred. Preserve the UUID/request and follow the normal same-ID retry rules;
do not invent a new UUID or reuse unreleased source paths to resolve uncertainty.

## Check with OpenSSL directly

This POSIX client example uses GNU `timeout` to bound the diagnostic process.
Use the same authority, request file and PEM credentials as above:

```sh
authority=mover.example.internal:8443
hostname=mover.example.internal
{
  printf 'POST /api/v2/jobs HTTP/1.1\r\nHost: %s\r\nContent-Type: application/json\r\nContent-Length: %s\r\nConnection: close\r\n\r\n' \
    "$authority" "$(wc -c <submission.json)"
  cat submission.json
} | timeout 15s openssl s_client \
  -connect "$authority" -servername "$hostname" \
  -verify_hostname "$hostname" -verify_return_error \
  -CAfile server-root.pem -cert approved-client.pem -key approved-client.key.pem \
  -tls1_2 -alpn http/1.1 -quiet -ign_eof -no_ticket
```

Use `-tls1_3` for TLS1.3. Keep `-alpn http/1.1`: the server requires this
negotiated application protocol. Keep `-quiet`: ordinary s_client diagnostics can include
TLS session secrets. Its process exit status reports TLS/process success;
inspect the returned HTTP status and JSON as well. Verification errors and timeouts
are failures, even if a TCP connection was established.

## Certificate changes and failures

After the host-local reload procedure in the setup guide, verify the active
PID:start, generation and public policy hash with the matching executable's
`--tls-status`. Recheck the actual HTTPS endpoint with the replacement client.
Saving the configuration also makes the replacement policy available at restart.

Removing a leaf's approval while keeping its CA trusted produces HTTP403 after
TLS succeeds. Removing its trusted client CA prevents TLS authentication.
The independent checks cover server-leaf replacement under the same server CA,
client-leaf approval changes, client-CA replacement, invalid-policy refusal and
original-state restarts. They do not qualify a server-CA rollover or every PKI
revocation mechanism.

| Observation | Action |
|---|---|
| curl 60 / OpenSSL verification error | Check hostname, trust and certificate validity on both sides; preserve verification |
| Explicit incoming TLS client-certificate alert (curl 35/56/60/98) | Check supplied certificate/key, client usage/validity and server client-CA policy |
| HTTP403 with valid TLS | Check approved leaf fingerprint, generator, source scope and producer-only route |
| CLI option error | Check the client version and supported syntax; this does not test the server |
| Connection failure or timeout | Diagnose reachability/service state; preserve submission identity if admission is uncertain |
| Invalid reload refused | Inspect status and the intended policy; the previous policy remains active after validation refusal |

Curl can map a peer's expired-client alert to generic code60. Use the OpenSSL
diagnostic or controlled client traces to distinguish an incoming peer rejection
from a local server-verification failure. The qualification harness requires the
actual incoming alert; a generic error, outgoing alert or timeout cannot pass.

## Reproduce the disposable qualification

On the Linux/WSL qualification host, with both digest-pinned images cached and a
retained PASSED production gate containing matching source/ELF/binary artifacts:

```sh
python3 -m unittest discover -s scripts -p 'test_tls_client*.py'
python3 scripts/check-tls-clients.py \
  --production-gate rust/validation/PRODUCTION_GATE \
  --report rust/validation/tls-clients-NEW-RUN.json
```

Choose a new report path every run. The driver creates an internal network with
no published ports and separate unprivileged SLES server/client containers. It
generates fresh disposable credentials, converts client PEM files inside the
pinned client container, verifies actual tool/executable identities, runs both
production profiles and removes its owned containers/network. Private keys and
TLS session data are excluded from the report and installation inputs.

Not-yet-valid client certificates, other client versions/backends, literal
network-outage/pre-admission disconnects, installation bundles, systemd, physical
SLES/NFS/FIPS environments and full release remain separate qualifications.
