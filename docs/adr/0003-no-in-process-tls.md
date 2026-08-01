---
status: accepted
date: 2026-08-01
decision-makers: Joey
precedent: dashboard server on RHEL 9 (rootless Podman NGINX reverse proxy terminating TLS in front of Plotly Dash)
---

# Serve plaintext HTTP; terminate TLS at a reverse proxy if required

## Context and Problem Statement

STIG guidance requires TLS 1.2+ for encrypted transport where encryption is
mandated. SLES 12 ships OpenSSL 1.0.x. Linking and correctly configuring TLS
inside the daemon adds substantial code, certificate lifecycle handling, and
audit surface to a service intended for a controlled internal network.

## Decision Drivers

* Smallest possible in-process attack/audit surface
* Certificate lifecycle owned by infrastructure, not the application
* Established proxy-termination precedent in the environment

## Considered Options

* In-process TLS via system OpenSSL (cpp-httplib `CPPHTTPLIB_OPENSSL_SUPPORT`)
* Plaintext HTTP, TLS terminated by nginx/stunnel in front when mandated
* Plaintext HTTP, no TLS path at all

## Decision Outcome

Chosen option: **plaintext HTTP with proxy-terminated TLS when required**.
The daemon binds to a configured interface (loopback by default); if an
accreditation boundary requires TLS, an nginx or stunnel instance from the
SLES repositories terminates it without any application change.

### Consequences

* Good: zero crypto code in the daemon; cert rotation is an ops concern.
* Bad: a deployment checklist item exists (bind address + proxy) rather than
  a compile-time guarantee.
