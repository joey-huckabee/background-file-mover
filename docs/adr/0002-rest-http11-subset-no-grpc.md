---
status: accepted
date: 2026-08-01
decision-makers: Joey
precedent: mapservice-runtime, Leadline (REST/HTTP services; no gRPC anywhere in the portfolio)
---

# Expose a REST API over an HTTP/1.1 subset; do not implement gRPC

## Context and Problem Statement

The trigger interface was originally scoped as "REST or gRPC". gRPC requires
grpcio/protobuf toolchains that are impractical to build for GCC 4.8.5 and
air-gapped SLES 12 hosts. HTTP/2+ adds binary framing, HPACK, and stream
multiplexing with zero benefit for a five-endpoint internal API polled by a
single dashboard.

## Decision Drivers

* Minimal implementation and audit surface
* curl-debuggability on the target host
* Compatibility with vendored single-header servers

## Considered Options

* gRPC
* Full HTTP/1.1 (keep-alive, chunked encoding)
* HTTP/1.1 subset: GET/POST, Content-Length bodies, `Connection: close`

## Decision Outcome

Chosen option: **HTTP/1.1 subset with `Connection: close`**, because it is
fully conformant for the known clients (curl, browser fetch), eliminates
keep-alive and chunked-encoding state machines, and bounds request handling
to one connection per request with a hard request-size cap.

### Consequences

* Good: trivially testable; hostile-input surface is small and enumerable.
* Bad: no connection reuse (irrelevant at a 2-second dashboard poll rate).
* Bad: a future streaming requirement would force revisiting this ADR.
