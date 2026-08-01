---
status: accepted
date: 2026-08-01
decision-makers: Joey
precedent: none — first project in this line to require building inside the gcc:4.8 CI container
---

# Build with plain GNU Make

## Context and Problem Statement

SLES 12 ships an old CMake, and the gcc:4.8 CI container (Debian Jessie base)
has archived apt repositories, making CMake installation unreliable there.
The project is a handful of translation units with one test binary.

## Decision Drivers

* Identical build entry points on SLES 12, dev machines, and both CI jobs
* No build-system bootstrap on any target

## Considered Options

* CMake (>= 3.5 for SLES 12 compatibility)
* Plain GNU Make

## Decision Outcome

Chosen option: **plain GNU Make** with `make all` / `make check` / `make
clean`, `-std=c++11 -Wall -Wextra -Werror`, and `-isystem third_party` so
vendored headers do not trip `-Werror`.

### Consequences

* Good: works unmodified everywhere GCC 4.8.5 exists, including the CI
  container.
* Bad: no out-of-source multi-config generators; acceptable at this size.
  Revisit if the workspace grows past a dozen translation units.
