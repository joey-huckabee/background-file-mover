# Dashboard demo tool (WSL, development only)

`fm-demo` runs a disposable File Mover on your Windows machine through WSL, so you
can show the dashboard and its live updates. Throwaway state, certificates and
account; not a qualified build or deployment. Run from the repository root in
PowerShell or cmd:

```text
scripts\demo\fm-demo.cmd build                 # build from the WSL clone (~/GIT/background-file-mover-testing)
scripts\demo\fm-demo.cmd setup --jobs 12       # fresh demo with 12 delivered jobs
scripts\demo\fm-demo.cmd start                 # run it; prints the address and sign-in
scripts\demo\fm-demo.cmd status
scripts\demo\fm-demo.cmd add-job               # one new job (2 files, 3 MiB)
scripts\demo\fm-demo.cmd add-job --count 5 --interval 3
scripts\demo\fm-demo.cmd add-job --size-mb 400 # big enough to watch it progress
scripts\demo\fm-demo.cmd stop
scripts\demo\fm-demo.cmd reset                 # stop and delete all demo state
```

Open **https://localhost:9443/** (not `127.0.0.1`) and sign in as `admin` /
`review-demo-2026`. The browser warns about the test certificate; choose
Advanced → Continue. The test certificates expire after two days; run `setup`
again for fresh ones.

## Showing live updates

| Indicator next to Sign out | Meaning | How to show it |
|---|---|---|
| Live (green) | Page updates on its own | Sort Job ▼ (newest first), then `add-job` |
| Connecting… (yellow) | Opening the stream after sign-in | Visible briefly after signing in |
| Reconnecting… (yellow) | Stream dropped; browser retries every 5 s | `stop`, then `start`: it returns to Live |
| Live updates unavailable (red) | Stream refused or service unreachable; retries after 30 s | Open a third tab (two live pages at most) |

## How it works

- Native build with the SLES gate's SQLite compile options; the SLES gate in CI
  remains the qualification evidence.
- WSLg mirrors `/` at `/mnt/wslg/distro`, which the mover's mount-alias checks
  refuse by design. The service runs in a private mount namespace that hides that
  mirror ([`dev-wsl-namespace.sh`](../dev-wsl-namespace.sh)); nothing on the host
  changes.
- The service runs as the transient systemd unit `fm-demo-review`, so it keeps
  running after the command returns, until `stop` or a WSL restart.
- Jobs are submitted to the producer on `127.0.0.1:18080` (loopback HTTP) with
  random file contents under the demo source folder.
- Safety: the tool only ever deletes inside the demo user's own `~/fm-demo`
  (fixed path, no symlinks, owned by that user, with a `.fm-demo` marker created
  by `build`). Before deleting demo state or removing a leftover socket it proves
  through the mover's own instance lock (`--check-state`) that no mover owns the
  state. A failed `setup` always stops the service it started. Internal steps
  refuse to run as root.
- Data lives in `~/fm-demo` inside WSL. Set `FM_DEMO_DISTRO` if your WSL
  distribution is not `Ubuntu`.
