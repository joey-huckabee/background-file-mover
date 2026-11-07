# E4: httparse compatibility

Run `python experiments/e4-http/run.py` with Podman on PATH. The harness builds
using Rust 1.99.0, the pinned cargo-zigbuild/Zig reference image and GNU/glibc
2.22 target with baseline x86-64 flags. It executes a std control, normal HTTP
probe, SIMD-disabled HTTP probe and cumulative HTTP/JSON/SQLite/rustix probes
in pinned SLES 12 SP5 userspace. Runtime programs run as UID/GID 1000 with
eager binding, no network access beyond container loopback and no capabilities.
Containers are removed; ignored `results/<run-id>/` retain all evidence.

The direct candidate is httparse 1.10.1, default features disabled, `std`
enabled, with no crate dependencies. The normal build retains runtime SSE4.2
and AVX2 dispatch. The published crate's build script disables SIMD only when
`CARGO_CFG_HTTPARSE_DISABLE_SIMD=1`; build.sh supplies it through
`--cfg httparse_disable_simd="1"` in RUSTFLAGS. A boolean cfg alone is
insufficient. The runner checks the build diagnostic and executable symbols
to prove the scalar variant excludes httparse SIMD/runtime-dispatch functions.
The scalar battery executes the SWAR fallback; normal dispatch executes on
the runner's CPU. Old CPU hardware and feature-masked emulation are not tested.

httparse owns request/header syntax. The experimental adapter supplies the
service's stricter CRLF and token policy, 64-header limit, duplicate rejection,
Content-Length/Transfer-Encoding rules, head/body size caps and extra-byte
rejection. It preserves original target bytes: for a non-UTF8 target it parses
a bounded, equal-length copy with high bytes replaced only in the target;
the returned target uses original bytes and framing offsets remain unchanged.
A C++ oracle confirms that compatibility case and all 37 original HTTP seeds.
The original corpus is never rewritten or classified solely by filename.

The parser battery exercises proper prefixes, normalization, exact resource
bounds, body completeness and 10000 deterministic corpus mutations. A bounded
loopback TCP fixture verifies hostile input, a 200ms absolute request deadline,
valid progress alongside a dribbling client, four-worker connection admission,
worker reaping, complete close-framed responses and continued service. Cumulative
cases repeat the E3 JSON battery and E1/E2 checks, then process a typed JSON POST
through a real SQLite transaction before returning 201. Rejected JSON creates
no row. This is a qualification fixture, not the final event loop or routing API.

ELF inspection enforces loader/library/glibc rules, and six negative audit
controls verify rejection. Hashes establish that inspected binaries are those
copied into SLES. Feature metadata, macro host commands, sources, vendor
archives, compiler flags and runtime output remain available. Recheck after
any compiler, dependency, feature or builder change. The WSL2 kernel is shared
with the containers; old-kernel execution and the user's own builder remain
unqualified. No NFS server is needed; its [fixture note](../../docs/NFS-TEST-FIXTURE.md)
remains available for later filesystem tests.

`--reuse-build <run-id>` verifies the retained source archive against current
experiment, C++ oracle and HTTP/JSON corpus inputs and pinned image settings,
then reruns audit/runtime checks. Changed build inputs require a fresh build.
