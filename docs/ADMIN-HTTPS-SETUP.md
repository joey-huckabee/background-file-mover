# Admin HTTPS sign-in setup

This guide enables browser sign-in on the separate admin HTTPS listener from
[increment130](RUST-INCREMENT-130.md). It does not authorize deployment or
changes to operational state. The signed-in page shows read-only job history and
job details ([increment131](RUST-INCREMENT-131.md)) and the retention ledger
([increment132](RUST-INCREMENT-132.md)); actions come later.

## What you need

1. Native ingress already configured (`native_ingress`, either transport). See
   [native HTTPS setup](NATIVE-HTTPS-SETUP.md).
2. A provisioned admin account. See [offline account setup](ADMIN-ACCOUNT-SETUP.md).
   Without one the service refuses to start; there is no setup page or default password.
3. A server certificate chain, PKCS8 key and trust anchors for the name browsers
   will use. These follow the same DER and file-permission rules as the producer
   listener ([prepare credentials](NATIVE-HTTPS-SETUP.md#prepare-credentials)).
   Browsers must trust the issuing CA. No client certificate is needed.

## Configure

Add an `admin_ingress` section to the service configuration:

```json
"admin_ingress": {
  "bind": "0.0.0.0:9443",
  "authority": "mover.example.internal:9443",
  "server_certificates": ["/etc/file-mover/admin-tls/server.der"],
  "server_key": "/etc/file-mover/admin-tls/server.key.der",
  "server_ca_certificates": ["/etc/file-mover/admin-tls/ca.der"],
  "account_directory": "/var/lib/file-mover-account",
  "inactivity_timeout_seconds": 1800
}
```

- `bind` is a separate address and port from the producer `bind`. Its port must
  equal the `authority` port. Unlike the producer HTTP mode, it may be non-loopback.
  It is always HTTPS; there is no plaintext mode.
- `authority` is the exact `host:port` browsers use, always with an explicit port.
  Requests with a different `Host`, or a login/logout `Origin` other than the
  browser form of this authority, are refused. On port 443 browsers omit the
  port (`https://host`); that form is accepted.
- Credential directories must be separate from the account directory, state,
  operator socket and payload roots, including destination roots still holding
  retained jobs from an earlier configuration. The account directory must also be separate
  from the producer credentials.
- `inactivity_timeout_seconds` defaults to 1800 (30 minutes).

Certificate changes on this listener need a stop and restart. The producer's
live TLS reload does not reload the admin listener.

## Use

Open `https://AUTHORITY/` and sign in with the account username and password.

- Five sign-in attempts per minute are allowed for the whole instance. After that,
  wait a minute. There is no permanent lockout.
- **Sign out everywhere** ends every dashboard session. Transfers keep running.
- Sessions end after the inactivity timeout. Background page loads do not extend
  a session; only deliberate activity does.
- Restarting the service ends every session.
- To change the password: stop the mover, run `--admin-password-change`
  ([guide](ADMIN-ACCOUNT-SETUP.md)), then start it. All sessions end.

Up to four admin connections are served at once, inside the service's global
limit of eight, with one slot always kept for the local operator. Extra
simultaneous connections are closed, not queued. Under a full producer load the
shared TLS workers may still refuse admin connections until producers finish.

## Troubleshooting

| Symptom | Meaning |
|---|---|
| Service exits with "requires a provisioned admin account" | Run `--admin-account-init` first |
| Browser certificate warning | Browser does not trust the issuing CA, or the name differs from `authority` |
| "Too many sign-in attempts" | Rate limit; wait one minute |
| "The service is busy" | Another sign-in was being checked, 64 sessions exist, or a sign-out happened during sign-in; retry |
| 403 on sign-in from a proxy or different hostname | `Origin`/`Host` must match `authority` exactly; proxies are not supported |
| "… is on a filesystem that is also mounted at …" | The account, credential or socket path can be reached through a second mount (an alias), which would bypass ownership checks. Use a filesystem mounted only once, or remove the extra bind mount. On WSL, WSLg mirrors `/` at `/mnt/wslg/distro`, so every WSL path is aliased; run the service on a real host or container, or set `guiApplications=false` in `.wslconfig` and restart WSL |
| "… is inside …, a bind mount of a subdirectory" | The path is under a bind mount of part of another filesystem. Use a directly mounted filesystem |
| "… is itself a mount point" | Configure a directory below the mount point, not the mount point itself |
| "… is on a nfs filesystem …" (or another type) | Account, credential and socket files must be on local ext2/3/4, tmpfs or overlay storage |

Startup and command errors start with `file-mover:` followed by the configuration
field (for example `admin_ingress.account_directory:`) and the reason.
