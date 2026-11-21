# Consumer guide: recordings and manifests (DOC-02)

For the program that picks up delivered recordings from the destination (the
**consumer**, for example an archive or processing job). It explains the
folder layout, how to tell that a recording is complete, and how to check it.
The exact manifest rules are in the
[producer and manifest contract](api/PRODUCER-MANIFEST-CONTRACT.md#manifest-v2-exact-writer-bytes-and-evidence).

Status: describes the current `main` implementation (increment 167). It is
user documentation, not release qualification; all eight release gates remain
open.

## Layout

Each recording gets its own folder directly under the configured destination
root, named by its recording UUID (lowercase):

```text
<destination root>/
  75507a61-f616-4e22-b462-8ef48be2f902/
    COMMITTED.json            <- appears last: the recording is complete
    session-002/audio.wav     <- the files, at the producer's relative paths
    session-002/notes.txt
    session-002/video.mkv
    .staging/                 <- the mover's work area: ignore it
```

- Files keep the exact relative paths the producer listed, including
  subfolders.
- The mover creates them read-only for its own service account (files `0400`,
  folders `0700`). It does not copy source owners, permissions, timestamps or
  extended attributes. How a consumer account gets read access is a
  deployment decision for the host administrator.
- `.staging/` holds the mover's in-progress copies. It may stay after
  completion, possibly empty. Never read from it or treat it as payload.
- Recordings accepted under the older protocol (still-tracked legacy jobs)
  use a numeric folder name and a version 1 manifest. New recordings always
  use the UUID and version 2.

## When a recording is complete

A recording is complete for you when `COMMITTED.json` is present **and**
it, and every file it lists, pass the checks below. Presence alone only makes
the folder a candidate. The mover:
1. copies each file into `.staging/`, verifies it and moves it to its final
   name;
2. only after **every** file is in place, publishes `COMMITTED.json` under
   its final name with its full contents (no partially written manifest is
   ever visible under that name);
3. then finishes its own bookkeeping: syncing to disk and recording the job as
   committed. `COMMITTED.json` can be visible before that finishes. If the
   host fails at that moment, the mover completes the same publication after
   restart, with the same bytes.

So:
- **No `COMMITTED.json` means not complete.** Do not consume the folder.
  Files may still be arriving. If the recording was cancelled, some files may
  stay without a manifest, and an operator may later delete them (**Delete
  partial destination files**).
- **`COMMITTED.json` present:** check it (next section). Once a recording
  passes, the mover never changes, replaces or removes its **listed files** or
  its `COMMITTED.json`. It may still remove leftover attempts inside
  `.staging/`. Clearing the job from the mover's history leaves the files where
  they are.
- The producer's 202 and the dashboard are not completion signals for you.
  The validated manifest is.

## Checking a recording

Do this before using a recording:

1. **Find candidates:** folders under the destination root that contain
   `COMMITTED.json`. Poll; the mover sends no notification.
2. **Read the manifest:** at most 131,072 bytes, UTF-8 JSON. Refuse
   duplicate or unknown fields. For version 2:

   | Field | Meaning |
   |---|---|
   | `version` | `2` |
   | `instance_id` | The mover installation (32 lowercase hex). |
   | `job_id` | The mover's job number (decimal string). |
   | `generator_id` | The producer's generator. |
   | `recording_id` | The recording UUID; equals the folder name. |
   | `request_identity` | `{"version":1,"algorithm":"sha256","sha256":…}`: a digest of the producer's original request. |
   | `files` | One entry per file, by `file_id` `"0"`, `"1"`, …: `path`, `size_bytes` (decimal string, the measured size), `algorithm` (`"sha256"`), `sha256` (64 lowercase hex). |

3. **Check the list before opening any file:**
   - `file_id`s are `"0"` through `"N-1"`, each once, in ascending numeric
     order, with N from 1 to 256;
   - each `path` is valid under the
     [producer path rules](api/PRODUCER-MANIFEST-CONTRACT.md#producer-request-and-lexical-rules):
     - relative, with no leading or trailing `/`;
     - no empty, `.` or `..` component;
     - no backslash or control characters;
     - no reserved component (`.file-mover`, `.control`, `.staging`,
       `COMMITTED.json`);
   - every path is unique, and no path is a folder of another path.
4. **Check every file,** opening each path component by component from the
   recording folder **without following symbolic links** (refuse a link at
   any level, not only the last). This keeps every read inside the recording
   folder.
   - The final component is a regular file.
   - Its size equals `size_bytes`.
   - Its SHA-256 equals `sha256`.
5. **Check that nothing else is there:** apart from `COMMITTED.json`,
   `.staging/` and the folders leading to listed files, the folder should
   contain nothing else.
6. **Optional, when you have the producer's request:**
   - the request's `recording_id` and `generator_id` match;
   - its file set equals the manifest's paths;
   - recompute the request identity
     ([REQUEST-IDENTITY](api/REQUEST-IDENTITY.candidate.md)) and compare it.
     The digest alone cannot rebuild the request.

If any check fails, do not use the recording and alert the operator with the
folder name and the failing check. The mover does not re-deliver a recording
once its manifest is published, so a lasting mismatch means something outside
the mover changed it, or the storage failed.

The manifest's hashes prove the files match what the mover delivered. They
are not a signature: anyone who can write the destination could change both.
Protect the destination with permissions.

## Rules of thumb

- Treat recording folders as **read-only**. Never write into a recording
  folder, rename files inside it or create `COMMITTED.json` yourself.
- **Moving or deleting a recording folder:**
  - In **copy mode** (the default), the mover keeps its own copy of each file
    on the source disk after delivery.
  - In **move mode** (`delete_source_after_commit`), the mover first checks
    the delivered folder, then removes its source copies one by one. Taking the
    folder away during that window can leave **no complete copy anywhere**.
  - So in move mode, move or delete a folder only after the operator confirms
    the job's source cleanup has **finished**: every file shows **Delivered,
    source removed** (status `files[].phase` = `SourceRemoved`). The absence
    of *Removing source* is not enough: cleanup can be paused, can resume
    after a restart or mode change, and a cleared job no longer shows any
    status.
  - If you cannot get that confirmation, copy the recording out and leave the
    folder in place.
- A recording UUID names exactly one folder. If a folder with that name
  already exists, the mover refuses to deliver into it rather than overwrite.
  So do not leave unrelated folders with UUID names in the destination.
- Ignore any folder without `COMMITTED.json`, and ignore `.staging/`.

## Related

- Producers: [producer quickstart](PRODUCER-QUICKSTART.md) (DOC-01).
- Operators: [status and recovery guide](RUST-OPERATOR-GUIDE.md).
