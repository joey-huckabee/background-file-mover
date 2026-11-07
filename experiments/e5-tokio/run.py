"""Qualify Tokio signals/runtime alone and with HTTP/JSON/SQLite/rustix in pinned SLES userspace."""
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
    print(f"E5 results: {results}", flush=True)
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
                        if member.name.startswith("corpus/"):
                            source = (ROOT.parent.parent / "cpp/fuzz/corpus-http" / member.name[7:]).resolve()
                            assert source.is_relative_to((ROOT.parent.parent / "cpp/fuzz/corpus-http").resolve())
                        elif member.name.startswith("json-corpus/"):
                            source = ROOT.parent.parent / "cpp/fuzz/corpus-json" / member.name[len("json-corpus/"):]
                        elif member.name == "reference/http_parser.cpp":
                            source = ROOT.parent.parent / "cpp/src/http_parser.cpp"
                        elif member.name == "reference/include/filemover/http_parser.hpp":
                            source = ROOT.parent.parent / "cpp/include/filemover/http_parser.hpp"
                        elif member.name == "reference/json.cpp":
                            source = ROOT.parent.parent / "cpp/src/json.cpp"
                        elif member.name == "reference/include/filemover/json.hpp":
                            source = ROOT.parent.parent / "cpp/include/filemover/json.hpp"
                        else:
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
            for name in ("Cargo.toml", "rust-toolchain.toml", "build.sh", "http-oracle.cpp", "json-oracle.cpp", "control", "probe", "json", "http", "cumulative"):
                command(PODMAN + ["cp", str(ROOT / name), f"{builder}:/work/{name}"])
            command(PODMAN + ["cp", str(ROOT.parent.parent / "cpp/fuzz/corpus-http"), f"{builder}:/work/corpus"])
            command(PODMAN + ["cp", str(ROOT.parent.parent / "cpp/fuzz/corpus-json"), f"{builder}:/work/json-corpus"])
            command(PODMAN + ["exec", builder, "mkdir", "-p", "/work/reference/include/filemover"])
            command(PODMAN + ["cp", str(ROOT.parent.parent / "cpp/src/json.cpp"), f"{builder}:/work/reference/json.cpp"])
            command(PODMAN + ["cp", str(ROOT.parent.parent / "cpp/include/filemover/json.hpp"), f"{builder}:/work/reference/include/filemover/json.hpp"])
            command(PODMAN + ["cp", str(ROOT.parent.parent / "cpp/src/http_parser.cpp"), f"{builder}:/work/reference/http_parser.cpp"])
            command(PODMAN + ["cp", str(ROOT.parent.parent / "cpp/include/filemover/http_parser.hpp"), f"{builder}:/work/reference/include/filemover/http_parser.hpp"])
            if (ROOT / "Cargo.lock").exists():
                command(PODMAN + ["cp", str(ROOT / "Cargo.lock"), f"{builder}:/work/Cargo.lock"])
            print("Building isolated and cumulative probes...", flush=True)
            try:
                command(PODMAN + ["exec", builder, "/bin/sh", "/work/build.sh"], results / "build-command.txt")
            finally:
                command(PODMAN + ["cp", f"{builder}:/work/evidence", str(results / "evidence")], check=False)
        evidence = results / "evidence"
        shutil.copyfile(evidence / "Cargo.lock", ROOT / "Cargo.lock")
        names = ("e5-control", "e5-tokio", "e5-cumulative")
        report["elf"] = {name: elf(evidence / "elf" / f"{name}.txt") for name in names}
        baseline = (evidence / "elf/e5-tokio.txt").read_text()
        bad_inputs = {
            "new-glibc": baseline.replace("@GLIBC_2.18", "@GLIBC_2.23"),
            "private-glibc": baseline.replace("@GLIBC_2.18", "@GLIBC_PRIVATE"),
            "wrong-loader": baseline.replace(CONFIG["interpreter"], "/lib64/ld-new.so"),
            "extra-shared-library": baseline + "\n (NEEDED) Shared library: [libsqlite3.so.0]\n",
            "runpath": baseline + "\n (RUNPATH) Library runpath: [/modern/lib]\n",
            "wrong-architecture": baseline.replace("Advanced Micro Devices X86-64", "AArch64"),
        }
        report["audit_negative_controls"] = []
        for label, invalid in bad_inputs.items():
            assert invalid != baseline
            path = results / ("audit-" + label + ".txt")
            path.write_text(invalid)
            try:
                elf(path)
            except AssertionError:
                report["audit_negative_controls"].append(label)
            else:
                raise AssertionError("audit accepted " + label)
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
        by_name = {package["name"]: package for package in metadata["packages"]}
        assert set(nodes[by_name["serde"]["id"]]["features"]) == {"std", "derive", "serde_derive"}
        assert set(nodes[by_name["serde_json"]["id"]]["features"]) == {"std"}
        assert set(nodes[by_name["httparse"]["id"]]["features"]) == {"std"}
        assert not nodes[by_name["httparse"]["id"]]["deps"]
        wanted = {"rt", "signal", "sync", "time", "net", "io-util"}
        selected = set(nodes[by_name["tokio"]["id"]]["features"])
        assert wanted <= selected
        assert not selected & {"full", "macros", "rt-multi-thread", "fs", "process", "parking_lot", "io-uring", "test-util"}
        assert "signal-hook" not in by_name and "signal-hook-registry" in by_name
        assert "tokio-macros" not in by_name
        report["tokio_selected_features"] = sorted(selected)
        host_ids = set()

        def host_walk(package_id):
            if package_id in host_ids:
                return
            host_ids.add(package_id)
            for dependency in nodes[package_id]["deps"]:
                host_walk(dependency["pkg"])

        host_walk(by_name["serde_derive"]["id"])
        report["macro_host_packages"] = sorted(package["name"] + "@" + package["version"] for package in metadata["packages"] if package["id"] in host_ids)
        macro_commands = [line for line in build_log.splitlines() if "Running `" in line and "--crate-type proc-macro" in line]
        assert macro_commands and all(" --target " not in line for line in macro_commands)
        report["macro_compiler_commands"] = macro_commands
        report["backend"] = "rustix default linux_raw in cumulative probe; serde derive macros run on builder"
        runtime = command(PODMAN + ["create", "--network", "none", "--cap-drop", "all", "--security-opt", "no-new-privileges", "--entrypoint", "/bin/sh", CONFIG["runtime"], "-c", "exec sleep infinity"]).strip()
        containers.append((PODMAN, runtime))
        command(PODMAN + ["start", runtime])
        inventory = command(PODMAN + ["exec", runtime, "/bin/sh", "-eu", "-c", 'cat /etc/os-release; getconf GNU_LIBC_VERSION; uname -r; rpm -qa | sort; test "$(getconf GNU_LIBC_VERSION)" = "glibc 2.22"; ! command -v cc; ! command -v cargo; ! command -v sqlite3'], results / "runtime-inventory.txt")
        assert 'VERSION_ID="12.5"' in inventory
        command(PODMAN + ["exec", runtime, "mkdir", "-p", "/tmp/e5-probe", "/tmp/e5-data"])
        command(PODMAN + ["exec", runtime, "chmod", "1777", "/tmp/e5-data"])
        command(PODMAN + ["cp", str(ROOT.parent.parent / "cpp/fuzz/corpus-http"), f"{runtime}:/tmp/e5-corpus"])
        command(PODMAN + ["cp", str(evidence / "oracle.tsv"), f"{runtime}:/tmp/e5-corpus/oracle.tsv"])
        for name in ("policy.tsv", "policy-raw-target"):
            command(PODMAN + ["cp", str(evidence / name), f"{runtime}:/tmp/e5-corpus/{name}"])
        report["cpp_policy_results"] = (evidence / "policy.tsv").read_text().splitlines()
        report["policy_fixture_hex"] = (evidence / "policy-raw-target").read_bytes().hex()
        command(PODMAN + ["cp", str(ROOT.parent.parent / "cpp/fuzz/corpus-json"), f"{runtime}:/tmp/e5-json-corpus"])
        command(PODMAN + ["cp", str(evidence / "json-oracle.tsv"), f"{runtime}:/tmp/e5-json-corpus/oracle.tsv"])
        report["json_corpus_hashes"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT.parent.parent / "cpp/fuzz/corpus-json").iterdir())}
        report["cpp_corpus_results"] = dict(line.split("\t") for line in (evidence / "oracle.tsv").read_text().splitlines())
        report["corpus_hashes"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT.parent.parent / "cpp/fuzz/corpus-http").iterdir())}
        report["hashes"] = {}
        for name in names:
            path = evidence / "artifacts" / name
            command(PODMAN + ["cp", str(path), f"{runtime}:/tmp/e5-probe/{name}"])
            command(PODMAN + ["exec", runtime, "chmod", "755", f"/tmp/e5-probe/{name}"])
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            assert command(PODMAN + ["exec", runtime, "sha256sum", f"/tmp/e5-probe/{name}"]).split()[0] == sha
            report["hashes"][name] = sha
            loaded = command(PODMAN + ["exec", runtime, "ldd", "-r", f"/tmp/e5-probe/{name}"], results / f"{name}-ldd.txt")
            assert "not found" not in loaded and "undefined symbol" not in loaded
        report["checks"] = {}

        def probe(engine, container, label, args, expected_nfs=False):
            output = command(engine + ["exec", "--user", "1000:1000", "--env", "LD_BIND_NOW=1", container, *args], results / f"{label}.txt", timeout=90)
            assert "RESULT PASS" in output, label
            if expected_nfs:
                assert "FILESYSTEM_TYPE 0x6969" in output, "not a kernel NFS filesystem"
            report["checks"][label] = output.splitlines()
            print(f"PASS {label}", flush=True)

        probe(PODMAN, runtime, "control", ["/tmp/e5-probe/e5-control", "/tmp/e5-data/control"])
        probe(PODMAN, runtime, "tokio-self", ["/tmp/e5-probe/e5-tokio", "self", "/tmp/e5-data/tokio-self"])
        probe(PODMAN, runtime, "cumulative-self", ["/tmp/e5-probe/e5-cumulative", "self", "/tmp/e5-data/cumulative-self", "/tmp/e5-corpus", "/tmp/e5-json-corpus"])

        def signal_case(binary, mode, labels, burst=False):
            import queue
            import threading
            label = binary + "-" + mode + "-" + "-".join(labels) + ("-burst" if burst else "")
            args = ["/tmp/e5-probe/" + binary, mode, "/tmp/e5-data/" + label]
            if binary == "e5-cumulative":
                args += ["/tmp/e5-corpus", "/tmp/e5-json-corpus"]
            process = subprocess.Popen(PODMAN + ["exec", "--user", "1000:1000", "--env", "LD_BIND_NOW=1", runtime, *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            mailbox = queue.Queue()
            lines = []
            def reader():
                for line in process.stdout:
                    mailbox.put(line)
                mailbox.put(None)
            thread = threading.Thread(target=reader, daemon=True)
            thread.start()
            deadline = time.monotonic() + 60
            ready = 0
            pid = None
            try:
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(label)
                    try:
                        line = mailbox.get(timeout=min(1,remaining))
                    except queue.Empty:
                        continue
                    if line is None:
                        break
                    lines.append(line.rstrip("\n"))
                    if line.startswith("READY "):
                        pid = int(line.split()[1])
                        assert pid > 1 and ready < len(labels)
                        signal_name = labels[ready]
                        if burst:
                            command(PODMAN + ["exec", "--user", "1000:1000", runtime, "/bin/sh", "-c", f"for i in 1 2 3 4 5 6 7 8 9 10; do kill -{signal_name} {pid}; done"])
                        else:
                            command(PODMAN + ["exec", "--user", "1000:1000", runtime, "kill", "-" + signal_name, str(pid)])
                        ready += 1
                process.wait(timeout=5)
                assert process.returncode == 0, "\n".join(lines)
                assert ready == len(labels) and "RESULT PASS" in lines
                report["checks"][label] = lines
                print("PASS " + label, flush=True)
            finally:
                (results / (label + ".txt")).write_text("\n".join(lines) + "\n")
                if process.poll() is None:
                    if pid:
                        command(PODMAN + ["exec", "--user", "1000:1000", runtime, "kill", "-KILL", str(pid)], check=False)
                    process.kill()
                    process.wait(timeout=5)

        for binary in ("e5-tokio", "e5-cumulative"):
            for signal_name in ("TERM", "INT"):
                signal_case(binary, "idle", [signal_name])
                signal_case(binary, "active", [signal_name])
            signal_case(binary, "active", ["TERM"], burst=True)
            signal_case(binary, "cycle", ["TERM", "INT", "TERM"])
        report["libraries_added"] = sorted(set(report["elf"]["e5-tokio"]["libraries"]) - set(report["elf"]["e5-control"]["libraries"]))
        report["status"] = "PASS"
        report["limitations"] = ["Pinned SLES userspace uses the WSL2 kernel; old kernel/CPU execution remains unqualified.", "Reference cargo-zigbuild; user's separate builder remains unqualified.", "Tokio current-thread configuration only; production task admission, NFS blocking isolation and shutdown escalation remain later work."]
        print("E5 PASS: Tokio reactor/signals/worker drain and cumulative HTTP/JSON/SQLite/rustix", flush=True)
        return 0
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        print(f"E5 FAILED: {error}", file=sys.stderr, flush=True)
        return 1
    finally:
        (results / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        for engine, container in reversed(containers):
            command(engine + ["rm", "--force", container], check=False)


if __name__ == "__main__":
    raise SystemExit(main())
