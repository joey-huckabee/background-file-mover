"""Supplement E5 with actual ENOSYS and pre-5.6 entropy flag behavior."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import run

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("run_id")
args = parser.parse_args()
results = (run.ROOT / "results" / args.run_id).resolve()
assert results.parent == (run.ROOT / "results").resolve()
report = json.loads((results / "report.json").read_text())
assert report["status"] == "PASS"
output = results / "entropy"
output.mkdir(exist_ok=True)
containers = []
checks = {}
try:
    builder = run.command(run.PODMAN + ["create", "--entrypoint", "/bin/sh", run.CONFIG["builder"], "-c", "mkdir -p /work; exec sleep infinity"]).strip()
    containers.append(builder)
    run.command(run.PODMAN + ["start", builder])
    run.command(run.PODMAN + ["cp", str(run.ROOT / "deny-random.c"), f"{builder}:/work/deny-random.c"])
    run.command(run.PODMAN + ["exec", builder, "zig", "cc", "-target", "x86_64-linux-gnu.2.22", "-mcpu=x86_64", "-O2", "/work/deny-random.c", "-o", "/work/deny-random"])
    run.command(run.PODMAN + ["cp", f"{builder}:/work/deny-random", str(output / "deny-random")])
    elf = run.command(run.PODMAN + ["exec", builder, "readelf", "-W", "-h", "-l", "-d", "-V", "--dyn-syms", "/work/deny-random"], output / "elf.txt")
    checks["helper_elf"] = run.elf(output / "elf.txt")
    runtime = run.command(run.PODMAN + ["create", "--network", "none", "--cap-drop", "all", "--security-opt", "no-new-privileges", "--entrypoint", "/bin/sh", run.CONFIG["runtime"], "-c", "exec sleep infinity"]).strip()
    containers.append(runtime)
    run.command(run.PODMAN + ["start", runtime])
    run.command(run.PODMAN + ["exec", runtime, "mkdir", "-p", "/tmp/e5-entropy"])
    run.command(run.PODMAN + ["exec", runtime, "chmod", "1777", "/tmp/e5-entropy"])
    for name, path in [("deny-random", output / "deny-random"), ("e5-tokio", results / "evidence/artifacts/e5-tokio")]:
        run.command(run.PODMAN + ["cp", str(path), f"{runtime}:/tmp/e5-entropy/{name}"])
        run.command(run.PODMAN + ["exec", runtime, "chmod", "755", f"/tmp/e5-entropy/{name}"])
        assert run.command(run.PODMAN + ["exec", runtime, "sha256sum", f"/tmp/e5-entropy/{name}"]).split()[0] == hashlib.sha256(path.read_bytes()).hexdigest()
    # Inspect actual SLES libc rather than infer optional symbol availability.
    run.command(run.PODMAN + ["cp", f"{runtime}:/lib64/libc.so.6", str(output / "sles-libc.so.6")])
    run.command(run.PODMAN + ["cp", str(output / "sles-libc.so.6"), f"{builder}:/work/sles-libc.so.6"])
    symbols = run.command(run.PODMAN + ["exec", builder, "readelf", "-W", "--dyn-syms", "/work/sles-libc.so.6"], output / "sles-libc-symbols.txt")
    checks["sles_getrandom_symbols"] = [line for line in symbols.splitlines() if "getrandom" in line]
    checks["runtime"] = run.command(run.PODMAN + ["exec", runtime, "getconf", "GNU_LIBC_VERSION"]).strip()
    assert checks["runtime"] == "glibc 2.22"
    checks["cases"] = {}
    for mode in ("old-flags", "enosys"):
        text = run.command(run.PODMAN + ["exec", "--user", "1000:1000", "--env", "LD_BIND_NOW=1", runtime, "/tmp/e5-entropy/deny-random", mode, "/tmp/e5-entropy/e5-tokio", "self", "/tmp/e5-entropy/" + mode], output / (mode + ".txt"))
        assert "FILTER VERIFIED " + mode in text and "RESULT PASS" in text
        checks["cases"][mode] = text.splitlines()
        print("PASS entropy " + mode, flush=True)
    checks["helper_sha256"] = hashlib.sha256((output / "deny-random").read_bytes()).hexdigest()
    checks["source_sha256"] = hashlib.sha256((run.ROOT / "deny-random.c").read_bytes()).hexdigest()
    checks["source"] = (run.ROOT / "deny-random.c").read_text()
    checks["status"] = "PASS"
finally:
    (output / "report.json").write_text(json.dumps(checks, indent=2) + "\n")
    for container in reversed(containers):
        run.command(run.PODMAN + ["rm", "--force", container], check=False)
