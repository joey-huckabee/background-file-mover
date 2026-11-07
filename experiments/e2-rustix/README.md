# Rustix compatibility experiment

E2 passed all twelve runtime phases with Rust 1.99, GNU/glibc 2.22 targeting,
and the same pinned SLES 12 SP5 image as E1. See the permanent
[result](../../docs/E2-RUSTIX-RESULTS.md) and
[evidence](../../docs/E2-RUSTIX-EVIDENCE.json).

The workspace contains a std control, a rustix filesystem probe, and a cumulative
probe with the accepted SQLite configuration. `deny-rename.c` is a test-only
seccomp launcher that returns ENOSYS or EOPNOTSUPP for the actual renameat2 syscall.
`Nfs.Containerfile` builds the controlled kernel NFS peer.

Run from the repository root with Python 3 and a running Podman connection:

```sh
python experiments/e2-rustix/run.py
```

The runner uses the pinned images in `images.json`. The modern builder requires
network access for pinned Rust/crate downloads. Compilation happens on native
container storage; the SLES runtime receives only the inspected executable.
Runtime tests use UID/GID 1000 and force eager loader binding.

The NFS fixture requires a rootful Podman connection named
`podman-machine-default-root`, with installed NFS client/server kernel modules
loaded. On this WSL2 setup, module preparation was:

```sh
wsl -d podman-machine-default -u root -- sh -lc 'modprobe nfs; modprobe nfsd'
```

The runner creates an internal network, a disposable export volume, and separate
server/client containers. It publishes no ports. Setup has mount privileges;
the probe itself runs as UID 1000. Results, binaries, source archives, and logs
are retained under ignored `results/<run ID>/` directories. Only IDs/names created
by that invocation are removed by cleanup.

If the build has already completed and only fixture setup changed, this reuses
the retained artifacts after checking every archived build source against the
current source tree and confirming the pinned image configuration:

```sh
python experiments/e2-rustix/run.py --reuse-build 20261013T032409Z-a3169ef2
```

The successful full run was `20261013T033910Z-f4cb8494`. The reference builder,
WSL2 kernel, CPU, and controlled NFS coverage limits are documented in the report.
