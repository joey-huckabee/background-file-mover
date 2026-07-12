# Feature interactions and combined use

The Background File Mover has several independently-configurable behaviours. Most combine
cleanly, but a few **interact** in ways that are not obvious from their individual
descriptions. This guide is for operators deciding *which options to enable together* and
what to expect from each combination. For the internal mechanism see
`docs/ARCHITECTURE.md` § *Feature interactions*; for per-option syntax see
`docs/CONFIG-REFERENCE.md` and `docs/CLI-REFERENCE.md`.

## The tunable behaviours

| Behaviour | Set by | Default |
|-----------|--------|---------|
| **Kernel-assisted copy** | `[transfer] use_kernel_copy` | `true` |
| **Bandwidth limit** | `[transfer] max_bytes_per_second`, live via `file-mover throttle` | `0` (unlimited) |
| **Partial-file resume** | `[transfer] resume_partial_files` | `true` |
| **Lifecycle control** | `file-mover pause` / `resume` / `cancel` | (operator action) |
| **Integrity mode** | `[integrity] mode` | `source-and-destination-hash` |

## The one thing to understand first: which copy engine runs

Every file is copied by **one of two engines**, chosen *per file, at the moment the copy
starts*:

- **Kernel-assisted** — `os.copy_file_range` moves bytes inside the kernel. Fastest for
  large files.
- **Buffered** — a userspace `read`/`write` loop. Slower, but it is the loop in which
  throttling happens.

The engine is chosen by this rule:

> **Buffered is used when** `use_kernel_copy = false`, **or** a bandwidth limit is active
> (`> 0`), **or** the source/destination pair does not support `copy_file_range` (an
> automatic, silent fallback). **Otherwise kernel-assisted is used.**

Everything else — **partial-file resume and pause/cancel work on _both_ engines**. Only the
**bandwidth limit** changes which engine runs.

> ### Q: Does partial-file resume affect the kernel-copy feature?
> **No.** Resume is fully compatible with kernel-assisted copy: it seeks both file
> descriptors to the partial's offset and `copy_file_range` continues from there; if the
> kernel copy has to fall back, it truncates to the *resume offset*, never to zero. Resume
> **never** forces the buffered path.
>
> The feature that *does* disable kernel copy is the **bandwidth limit** — a non-zero limit
> forces the buffered engine because the kernel cannot be paced from userspace. If you set
> a limit *and* enable resume, the resumed copy simply runs on the (already-forced) buffered
> engine. Enabling resume alone leaves kernel copy fully in play.

## Compatibility at a glance

|                     | Kernel copy | Bandwidth limit | Partial resume | Pause / cancel |
|---------------------|-------------|-----------------|----------------|----------------|
| **Kernel copy**     | —           | limit **forces buffered** | ✓ compatible | ✓ (stops at a buffer boundary) |
| **Bandwidth limit** | forces buffered | — | ✓ (resume runs buffered) | ✓ but low limit **slows** pause/shutdown |
| **Partial resume**  | ✓ compatible | ✓ | — | needs resume **enabled** to work |
| **Pause / cancel**  | ✓ | ✓ | relies on resume | — |

Cross-cutting: **integrity mode** governs how well a *resumed* copy is verified — see the
gotcha below.

## Pairwise interactions in detail

### Kernel copy × bandwidth limit — the limit wins

- **Mechanism.** Throttling happens in the userspace buffered loop; the kernel copy loop
  never consults the limiter. So any non-zero limit forces the buffered engine for every
  file copied while the limit is in force (L3-PY-011).
- **Consequence.** Turning on a bandwidth limit trades the kernel-copy fast path for
  throughput control. `file-mover throttle 0` restores kernel-copy eligibility.
- **Recommendation.** Only set a limit when you actually need to protect a shared link;
  leave it at `0` to keep the kernel fast path.

### Kernel copy × partial resume — compatible

- **Mechanism.** Resume reads the partial's size (`os.stat`), seeks both descriptors, and
  continues with whichever engine is selected; the kernel fallback truncates to the resume
  offset (L3-PY-012).
- **Consequence.** None — resume works at full kernel speed for the remaining bytes.
- **Recommendation.** Leave both enabled (the defaults).

### Kernel copy × pause/cancel — stops at a buffer boundary

- **Mechanism.** The pause/cancel signal is polled once per buffer in *both* engines
  (between `copy_file_range` chunks and between buffered writes).
- **Consequence.** A pause or cancel takes effect within roughly one
  `copy_buffer_size_bytes` chunk (8 MiB by default) — near-instant, not mid-write. The
  already-copied bytes are fsynced (pause) or discarded (cancel).
- **Recommendation.** If you want finer pause granularity, lower `copy_buffer_size_bytes`
  (at some throughput cost).

### Bandwidth limit × pause/cancel & shutdown — low limits add latency

- **Mechanism.** In the buffered loop the interrupt is checked *after* each chunk's throttle
  sleep. A very low limit means each chunk sleeps a long time.
- **Consequence.** With a low limit, a `pause`/`cancel` — and the graceful-shutdown drain —
  may wait up to `copy_buffer_size_bytes ÷ max_bytes_per_second` seconds for the current
  chunk to finish. Example: 8 MiB buffer at 1 MB/s ≈ 8 s worst-case.
- **Recommendation.** For responsive control under a tight limit, reduce
  `copy_buffer_size_bytes`, and keep `[service] shutdown_timeout_seconds` comfortably above
  that worst-case.

### Runtime `throttle` × an in-flight kernel copy — applies from the next file

- **Mechanism.** The copy engine is chosen at the *start* of each file. A file already
  copying on the kernel engine does not consult the limiter, so a mid-copy `throttle` does
  not slow it.
- **Consequence.** `file-mover throttle 50MB` while a large file is being kernel-copied
  will **not** slow that file; the limit takes effect from the next file. (A copy already on
  the buffered engine *does* respond to a live rate change.)
- **Recommendation.** Set the limit in config, or issue `throttle` before a run starts, if
  you need it to govern the very first large file.

### Partial resume × pause/resume lifecycle — resume must be enabled

- **Mechanism.** Pausing an in-flight copy always keeps the fsynced partial. Resuming the
  job re-copies with `resume = resume_partial_files`.
- **Consequence.** With `resume_partial_files = true` (default), `resume` continues the
  partial exactly. With it **`false`**, pausing an in-flight copy **drops** the partial (it
  could not be resumed cleanly), so `resume` simply **restarts that file from byte zero** and
  completes — no failure. Either setting is safe; the difference is whether resume continues
  or restarts.
- **Recommendation.** Keep `resume_partial_files = true` (default) if you want `resume` to
  continue large files where they left off rather than re-copy them.

### Partial resume × integrity mode — crash-safety depends on the mode

- **Mechanism.** A *pause* fsyncs the partial, so its prefix is durable and correct. A
  *crash* can leave a torn (partially-written) final buffer. On resume the bytes before the
  offset are trusted; whether a torn prefix is caught depends on the integrity mode, because
  only `source-and-destination-hash` re-hashes the destination content.
- **Consequence.** Under the default `source-and-destination-hash`, a torn resumed partial
  fails the hash check and is discarded and restarted (L2-RSM-003) — safe. Under `metadata`
  or `source-hash`, only the **size** is checked, so a crash-torn partial that happens to be
  the right size could be **published with corrupt content**.
- **Recommendation.** Keep `integrity.mode = source-and-destination-hash` whenever
  `resume_partial_files` is enabled. If you must use a weaker mode, consider disabling resume
  so every interrupted file restarts from a clean, full copy.

### Partial resume × crash recovery — keep vs remove partials

- **Mechanism.** Startup recovery re-queues interrupted jobs. With resume enabled it *keeps*
  their partials (to continue); with resume disabled it *removes* them (to restart from
  zero) (L2-RSM-002).
- **Consequence.** After a crash, enabling resume avoids re-copying already-transferred
  bytes; disabling it guarantees a clean full re-copy at the cost of repeating work.
- **Recommendation.** Keep resume enabled with a hash integrity mode for the best of both:
  fast recovery with a verified restart fallback.

## Recommended configurations by goal

| Goal | `use_kernel_copy` | `max_bytes_per_second` | `resume_partial_files` | `integrity.mode` |
|------|-------------------|------------------------|------------------------|------------------|
| **Maximum throughput** (dedicated link) | `true` | `0` | `true` | `source-and-destination-hash` |
| **Shared-link friendly** (bounded impact) | `true`¹ | e.g. `52428800` (50 MB/s) | `true` | `source-and-destination-hash` |
| **Strongest integrity + safe resume** | `true` | `0` | `true` | `source-and-destination-hash` |
| **Simplest / most conservative** | `true` | `0` | `false` | `source-and-destination-hash` |

¹ Kernel copy is automatically bypassed whenever the limit is active; leaving
`use_kernel_copy = true` means the fast path resumes as soon as you `throttle 0`.

## Gotchas — quick reference

- **A bandwidth limit disables kernel copy** while active (forces the buffered engine).
- **`throttle` does not slow a file already being kernel-copied** — it applies from the next
  file.
- **`pause`/`resume` honours `resume_partial_files`**: enabled resumes from the partial
  offset; disabled drops the partial on pause and restarts the file from zero on resume.
- **Resume + a weak integrity mode is not crash-safe** — keep
  `source-and-destination-hash` when resume is enabled.
- **A low bandwidth limit slows `pause`/`cancel` and shutdown** by up to one buffer's worth
  of sleep; lower `copy_buffer_size_bytes` for tighter control.
