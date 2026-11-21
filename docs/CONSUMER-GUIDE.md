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

**`COMMITTED.json` is the only completion signal.** The mover:
1. copies each file into `.staging/`, verifies it and moves it to its final
   name;
2. only after **every** file is in place, publishes `COMMITTED.json` in one
   step (no partial file is ever visible under that name).

So:
- **No `COMMITTED.json` means not complete.** Do not consume the folder. Files
  may still be arriving. If the recording was cancelled, some files may stay
  without a manifest, and an operator may later delete them (**Delete partial
  destination files**).
- **`COMMITTED.json` present:** the mover never changes, replaces or removes
  that folder's files or manifest again. Clearing the job from the mover's
  history leaves the files where they are.
- The producer's 202 and the dashboard are not completion signals for you.
  The manifest is.

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

3. **Check every file:**
   - `path` exists in the folder and is a regular file, not a link;
   - its size equals `size_bytes`;
   - its SHA-256 equals `sha256`.
4. **Check that nothing else is there:** apart from `COMMITTED.json`,
   `.staging/` and the folders leading to listed files, the folder should
   contain nothing else.
5. **Optional, when you have the producer's request:**
   - the request's `recording_id` and `generator_id` match;
   - its file set equals the manifest's paths;
   - recompute the request identity
     ([REQUEST-IDENTITY](api/REQUEST-IDENTITY.candidate.md)) and compare it.
     The digest alone cannot rebuild the request.

If any check fails, do not use the recording and alert the operator with the
folder name and the failing check. The mover does not re-deliver a committed
recording, so a mismatch after commit means something outside the mover
changed it.

The manifest's hashes prove the files match what the mover delivered. They
are not a signature: anyone who can write the destination could change both.
Protect the destination with permissions.

## Rules of thumb

- Treat recording folders as **read-only**. Never write into a recording
  folder, rename files inside it or create `COMMITTED.json` yourself.
- To take a recording away (move or delete the whole folder), check first.
  In **move mode** (`delete_source_after_commit`), the mover re-checks the
  delivered folder before removing its own source copy. If you remove the
  folder first, the mover keeps its source copy and flags the job under
  **Needs attention**. Nothing is lost, but an operator must deal with it. Wait
  until the job no longer shows *Removing source* before taking the folder
  away.
- A recording UUID names exactly one folder. If a folder with that name
  already exists, the mover refuses to deliver into it rather than overwrite.
  So do not leave unrelated folders with UUID names in the destination.
- Ignore any folder without `COMMITTED.json`, and ignore `.staging/`.

## Related

- Producers: [producer quickstart](PRODUCER-QUICKSTART.md) (DOC-01).
- Operators: [status and recovery guide](RUST-OPERATOR-GUIDE.md).
