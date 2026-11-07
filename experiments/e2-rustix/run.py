"""Qualify rustix alone and with SQLite in pinned SLES/glibc 2.22 userspace."""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import time
import uuid

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "images.json").read_text())
PODMAN = ["podman"]
ROOTFUL = ["podman", "--connection", "podman-machine-default-root"]


def command(args, log=None, check=True, timeout=900):
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as error:
        def decode(value):
            return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else (value or "")
        if log:
            log.write_text(decode(error.stdout) + decode(error.stderr), encoding="utf-8")
        raise
    output = result.stdout + result.stderr
    if log:
        log.write_text(output, encoding="utf-8")
    if check and result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(args)}\n{output[-5000:]}")
    return output


def elf(path):
    text = path.read_text()
    assert re.search(r"Machine:\s+Advanced Micro Devices X86-64", text), "wrong architecture"
    loader = re.search(r"Requesting program interpreter: ([^\]]+)", text)
    assert loader and loader[1] == CONFIG["interpreter"], "wrong ELF interpreter"
    assert not re.search(r"\((?:RPATH|RUNPATH)\)", text), "runtime library search path"
    libraries = sorted(set(re.findall(r"\(NEEDED\).*Shared library: \[([^\]]+)\]", text)))
    assert not set(libraries) - set(CONFIG["allowed_libraries"]), "unexpected library"
    symbols = sorted(set(re.findall(r"\bUND[ \t]+(\S+)", text)))
    versions = sorted(set(re.findall(r"@((?:GLIBC|GCC)_[\w.]+)", "\n".join(symbols))))
    glibc = []
    for version in versions:
        if version.startswith("GLIBC_"):
            assert re.fullmatch(r"GLIBC_\d+(?:\.\d+)+", version), version
            numbers = tuple(map(int, version[6:].split(".")))
            assert numbers <= (2, 22), version
            glibc.append(version)
    assert not any(symbol.startswith("renameat2@") for symbol in symbols), "new glibc renameat2 wrapper"
    return {"loader": loader[1], "libraries": libraries, "symbols": symbols,
            "versions": versions, "maximum_glibc": max(glibc, key=lambda v: tuple(map(int, v[6:].split("."))))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse-build", help="Reuse an unchanged retained build by run ID")
    options = parser.parse_args()
    label = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    results = ROOT / "results" / label
    results.mkdir(parents=True)
    print(f"E2 results: {results}", flush=True)
    report = {"status": "FAILED", "images": CONFIG, "run_id": label}
    containers = []
    network = volume = server = None
    try:
        for role in ("builder", "runtime"):
            command(PODMAN + ["image", "inspect", CONFIG[role]], results / f"{role}-image.json")
        command(PODMAN + ["info", "--format", "json"], results / "engine.json")
        if options.reuse_build:
            prior = (ROOT / "results" / options.reuse_build).resolve()
            assert prior.parent == (ROOT / "results").resolve()
            assert json.loads((prior / "report.json").read_text())["images"] == CONFIG
            with tarfile.open(prior / "evidence/probe-sources.tar.gz") as archive:
                for member in archive.getmembers():
                    if member.isfile():
                        source = (ROOT / member.name).resolve()
                        assert source.is_relative_to(ROOT)
                        assert source.read_bytes() == archive.extractfile(member).read(), member.name
            shutil.copytree(prior / "evidence", results / "evidence")
            report["reused_build"] = options.reuse_build
            print("Reusing retained build with verified unchanged source inputs...", flush=True)
        else:
            builder = command(PODMAN + ["create", "--entrypoint", "/bin/sh", CONFIG["builder"], "-c", "mkdir -p /work; exec sleep infinity"]).strip()
            containers.append((PODMAN, builder))
            command(PODMAN + ["start", builder])
            for name in ("Cargo.toml", "rust-toolchain.toml", "build.sh", "deny-rename.c", "control", "probe", "cumulative"):
                command(PODMAN + ["cp", str(ROOT / name), f"{builder}:/work/{name}"])
            if (ROOT / "Cargo.lock").exists():
                command(PODMAN + ["cp", str(ROOT / "Cargo.lock"), f"{builder}:/work/Cargo.lock"])
            print("Building isolated and cumulative probes...", flush=True)
            try:
                command(PODMAN + ["exec", builder, "/bin/sh", "/work/build.sh"], results / "build-command.txt")
            finally:
                command(PODMAN + ["cp", f"{builder}:/work/evidence", str(results / "evidence")], check=False)
        evidence = results / "evidence"
        shutil.copyfile(evidence / "Cargo.lock", ROOT / "Cargo.lock")
        names = ("e2-control", "e2-rustix", "e2-cumulative", "deny-rename")
        report["elf"] = {name: elf(evidence / "elf" / f"{name}.txt") for name in names}
        metadata = json.loads((evidence / "metadata.json").read_text())
        nodes = {node["id"]: node for node in metadata["resolve"]["nodes"]}
        report["dependencies"] = []
        for package in metadata["packages"]:
            if package["id"] in nodes and package["source"]:
                license = package["license"]
                assert "MIT" in license or "Apache-2.0" in license, (package["name"], license)
                report["dependencies"].append({"name": package["name"], "version": package["version"], "license": license, "features": nodes[package["id"]]["features"]})
                if package["name"] == "rustix":
                    assert not set(nodes[package["id"]]["features"]) & {"linux_latest", "linux_5_1", "linux_5_11", "io_uring", "use-libc"}
        # The verbose compiler cfg establishes the actual default Linux raw backend.
        build_log = (evidence / "build.log").read_text()
        assert 'feature="use-libc"' not in build_log
        report["backend"] = "rustix default linux_raw on x86_64 Linux"
        runtime = command(PODMAN + ["create", "--network", "none", "--cap-drop", "all", "--security-opt", "no-new-privileges", "--entrypoint", "/bin/sh", CONFIG["runtime"], "-c", "exec sleep infinity"]).strip()
        containers.append((PODMAN, runtime))
        command(PODMAN + ["start", runtime])
        inventory = command(PODMAN + ["exec", runtime, "/bin/sh", "-eu", "-c", 'cat /etc/os-release; getconf GNU_LIBC_VERSION; uname -r; rpm -qa | sort; test "$(getconf GNU_LIBC_VERSION)" = "glibc 2.22"; ! command -v cc; ! command -v cargo; ! command -v sqlite3'], results / "runtime-inventory.txt")
        assert 'VERSION_ID="12.5"' in inventory
        command(PODMAN + ["exec", runtime, "mkdir", "-p", "/tmp/e2-probe", "/tmp/e2-data"])
        command(PODMAN + ["exec", runtime, "chmod", "1777", "/tmp/e2-data"])
        report["hashes"] = {}
        for name in names:
            path = evidence / "artifacts" / name
            command(PODMAN + ["cp", str(path), f"{runtime}:/tmp/e2-probe/{name}"])
            command(PODMAN + ["exec", runtime, "chmod", "755", f"/tmp/e2-probe/{name}"])
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            assert command(PODMAN + ["exec", runtime, "sha256sum", f"/tmp/e2-probe/{name}"]).split()[0] == sha
            report["hashes"][name] = sha
            loaded = command(PODMAN + ["exec", runtime, "ldd", "-r", f"/tmp/e2-probe/{name}"], results / f"{name}-ldd.txt")
            assert "not found" not in loaded and "undefined symbol" not in loaded
        report["checks"] = {}

        def probe(engine, container, label, args, expected_nfs=False):
            output = command(engine + ["exec", "--user", "1000:1000", "--env", "LD_BIND_NOW=1", container, *args], results / f"{label}.txt", timeout=90)
            assert "RESULT PASS" in output, label
            if expected_nfs:
                assert "FILESYSTEM_TYPE 0x6969" in output, "not a kernel NFS filesystem"
            report["checks"][label] = output.splitlines()
            print(f"PASS {label}", flush=True)

        probe(PODMAN, runtime, "control", ["/tmp/e2-probe/e2-control", "/tmp/e2-data/control"])
        for binary in ("e2-rustix", "e2-cumulative"):
            for mode in ("rename", "fallback", "enosys", "notsup"):
                args = [f"/tmp/e2-probe/{binary}", f"/tmp/e2-data/{binary}-{mode}", mode]
                if mode in ("enosys", "notsup"):
                    args = ["/tmp/e2-probe/deny-rename", "38" if mode == "enosys" else "95", *args]
                probe(PODMAN, runtime, f"{binary}-{mode}", args)

        print("Starting controlled kernel NFSv4 fixture...", flush=True)
        command(ROOTFUL + ["build", "--tag", "localhost/background-file-mover-e2-nfs", "--file", str(ROOT / "Nfs.Containerfile"), str(ROOT)], results / "nfs-image-build.txt")
        server_image = command(ROOTFUL + ["image", "inspect", "localhost/background-file-mover-e2-nfs", "--format", "{{.Id}}"]).strip()
        report["nfs_server_image"] = server_image
        network = "e2-nfs-" + label.lower()
        volume = "e2-nfs-data-" + label.lower()
        command(ROOTFUL + ["network", "create", "--internal", network])
        command(ROOTFUL + ["volume", "create", volume])
        server = command(ROOTFUL + ["create", "--privileged", "--network", network, "--volume", f"{volume}:/exports", server_image]).strip()
        containers.append((ROOTFUL, server))
        command(ROOTFUL + ["start", server])
        ready = False
        for _ in range(40):
            logs = command(ROOTFUL + ["logs", server], check=False)
            if "NFS_READY" in logs:
                ready = True
                break
            time.sleep(0.5)
        (results / "nfs-server.txt").write_text(logs)
        assert ready, logs
        command(ROOTFUL + ["exec", server, "dpkg-query", "-W"], results / "nfs-server-packages.txt")
        server_data = json.loads(command(ROOTFUL + ["inspect", server]))[0]
        server_ip = server_data["NetworkSettings"]["Networks"][network]["IPAddress"]
        client = command(ROOTFUL + ["create", "--network", network, "--cap-drop", "all", "--cap-add", "SYS_ADMIN", "--security-opt", "no-new-privileges", "--entrypoint", "/bin/sh", CONFIG["runtime"], "-c", "exec sleep infinity"]).strip()
        containers.append((ROOTFUL, client))
        command(ROOTFUL + ["start", client])
        command(ROOTFUL + ["exec", client, "mkdir", "-p", "/tmp/nfs", "/tmp/e2-probe"])
        command(ROOTFUL + ["exec", client, "mount", "-i", "-t", "nfs4", "-o", f"addr={server_ip},vers=4.1,proto=tcp,port=2049,soft,timeo=10,retrans=1", f"{server_ip}:/", "/tmp/nfs"], results / "nfs-mount.txt", timeout=45)
        command(ROOTFUL + ["exec", client, "cat", "/proc/mounts"], results / "nfs-client-mounts.txt")
        for name in ("e2-rustix", "deny-rename"):
            command(ROOTFUL + ["cp", str(evidence / "artifacts" / name), f"{client}:/tmp/e2-probe/{name}"])
            command(ROOTFUL + ["exec", client, "chmod", "755", f"/tmp/e2-probe/{name}"])
        for mode in ("fallback", "enosys", "notsup"):
            args = ["/tmp/e2-probe/e2-rustix", f"/tmp/nfs/{mode}", mode]
            if mode != "fallback":
                args = ["/tmp/e2-probe/deny-rename", "38" if mode == "enosys" else "95", *args]
            probe(ROOTFUL, client, f"nfs-{mode}", args, expected_nfs=True)
        command(ROOTFUL + ["exec", client, "umount", "/tmp/nfs"])
        report["status"] = "PASS"
        report["limitations"] = ["SLES userspace on WSL2 kernel; Linux 4.12 and old CPU hardware not executed.", "Controlled modern kernel NFSv4 server, not production mount/server qualification.", "Reference cargo-zigbuild; user's separate builder remains unqualified."]
        print("E2 PASS: isolated, cumulative, forced syscall errors, and kernel NFSv4", flush=True)
        return 0
    except Exception as error:
        report["error"] = str(error)
        print(f"E2 FAILED: {error}", file=sys.stderr, flush=True)
        return 1
    finally:
        (results / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        if server:
            command(ROOTFUL + ["exec", server, "rpc.nfsd", "0"], check=False)
            command(ROOTFUL + ["exec", server, "exportfs", "-au"], check=False)
        for engine, container in reversed(containers):
            command(engine + ["rm", "--force", container], check=False)
        if volume:
            command(ROOTFUL + ["volume", "rm", volume], check=False)
        if network:
            command(ROOTFUL + ["network", "rm", network], check=False)


if __name__ == "__main__":
    raise SystemExit(main())
