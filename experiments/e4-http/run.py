"""Qualify httparse policy and TCP alone and with JSON/SQLite/rustix in pinned SLES userspace."""
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
    print(f"E4 results: {results}", flush=True)
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
            for name in ("Cargo.toml", "rust-toolchain.toml", "build.sh", "http-oracle.cpp", "json-oracle.cpp", "control", "probe", "json", "cumulative"):
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
        names = ("e4-control", "e4-http", "e4-cumulative", "e4-http-scalar")
        report["elf"] = {name: elf(evidence / "elf" / f"{name}.txt") for name in names}
        baseline = (evidence / "elf/e4-http.txt").read_text()
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
        report["cpu_build_flags"] = {"normal": "-C target-cpu=x86-64", "scalar": '-C target-cpu=x86-64 --cfg httparse_disable_simd="1"'}
        report["httparse_compile_commands"] = [line for line in build_log.splitlines() if "Running `" in line and "--crate-name httparse " in line]
        scalar_log = (evidence / "scalar-build.log").read_text()
        report["httparse_scalar_compile_commands"] = [line for line in scalar_log.splitlines() if "Running `" in line and "--crate-name httparse " in line]
        assert report["httparse_scalar_compile_commands"] and all("httparse_disable_simd" in line for line in report["httparse_scalar_compile_commands"]), "missing scalar compiler cfg"
        assert "CARGO_CFG_HTTPARSE_DISABLE_SIMD=1" in scalar_log, "missing published-crate disable value"
        assert "disabling SIMD" in scalar_log
        report["cpu_symbols"] = {}
        for name in names:
            lines = (evidence / "elf" / (name + "-symbols.txt")).read_text().splitlines()
            report["cpu_symbols"][name] = [line for line in lines if "httparse::simd::" in line]
        assert any("::avx2::" in line for line in report["cpu_symbols"]["e4-http"])
        assert any("::sse42::" in line for line in report["cpu_symbols"]["e4-http"])
        assert not any("::avx2::" in line or "::sse42::" in line or "::runtime::" in line for line in report["cpu_symbols"]["e4-http-scalar"])
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
        command(PODMAN + ["exec", runtime, "mkdir", "-p", "/tmp/e4-probe", "/tmp/e4-data"])
        command(PODMAN + ["exec", runtime, "chmod", "1777", "/tmp/e4-data"])
        command(PODMAN + ["cp", str(ROOT.parent.parent / "cpp/fuzz/corpus-http"), f"{runtime}:/tmp/e4-corpus"])
        command(PODMAN + ["cp", str(evidence / "oracle.tsv"), f"{runtime}:/tmp/e4-corpus/oracle.tsv"])
        for name in ("policy.tsv", "policy-raw-target"):
            command(PODMAN + ["cp", str(evidence / name), f"{runtime}:/tmp/e4-corpus/{name}"])
        report["cpp_policy_results"] = (evidence / "policy.tsv").read_text().splitlines()
        report["policy_fixture_hex"] = (evidence / "policy-raw-target").read_bytes().hex()
        command(PODMAN + ["cp", str(ROOT.parent.parent / "cpp/fuzz/corpus-json"), f"{runtime}:/tmp/e4-json-corpus"])
        command(PODMAN + ["cp", str(evidence / "json-oracle.tsv"), f"{runtime}:/tmp/e4-json-corpus/oracle.tsv"])
        report["json_corpus_hashes"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT.parent.parent / "cpp/fuzz/corpus-json").iterdir())}
        report["cpp_corpus_results"] = dict(line.split("\t") for line in (evidence / "oracle.tsv").read_text().splitlines())
        report["corpus_hashes"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT.parent.parent / "cpp/fuzz/corpus-http").iterdir())}
        report["hashes"] = {}
        for name in names:
            path = evidence / "artifacts" / name
            command(PODMAN + ["cp", str(path), f"{runtime}:/tmp/e4-probe/{name}"])
            command(PODMAN + ["exec", runtime, "chmod", "755", f"/tmp/e4-probe/{name}"])
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            assert command(PODMAN + ["exec", runtime, "sha256sum", f"/tmp/e4-probe/{name}"]).split()[0] == sha
            report["hashes"][name] = sha
            loaded = command(PODMAN + ["exec", runtime, "ldd", "-r", f"/tmp/e4-probe/{name}"], results / f"{name}-ldd.txt")
            assert "not found" not in loaded and "undefined symbol" not in loaded
        report["checks"] = {}

        def probe(engine, container, label, args, expected_nfs=False):
            output = command(engine + ["exec", "--user", "1000:1000", "--env", "LD_BIND_NOW=1", container, *args], results / f"{label}.txt", timeout=90)
            assert "RESULT PASS" in output, label
            if expected_nfs:
                assert "FILESYSTEM_TYPE 0x6969" in output, "not a kernel NFS filesystem"
            report["checks"][label] = output.splitlines()
            print(f"PASS {label}", flush=True)

        probe(PODMAN, runtime, "control", ["/tmp/e4-probe/e4-control", "/tmp/e4-data/control"])
        probe(PODMAN, runtime, "http", ["/tmp/e4-probe/e4-http", "/tmp/e4-corpus"])
        probe(PODMAN, runtime, "http-scalar", ["/tmp/e4-probe/e4-http-scalar", "/tmp/e4-corpus"])
        for mode in ("rename", "fallback"):
            probe(PODMAN, runtime, "cumulative-" + mode, ["/tmp/e4-probe/e4-cumulative", "/tmp/e4-corpus", "/tmp/e4-json-corpus", "/tmp/e4-data/" + mode, mode])
        assert report["elf"]["e4-http"]["libraries"] == report["elf"]["e4-control"]["libraries"], "HTTP added shared libraries"
        assert report["elf"]["e4-http-scalar"]["libraries"] == report["elf"]["e4-control"]["libraries"]
        report["status"] = "PASS"
        report["limitations"] = ["Pinned SLES userspace uses the WSL2 kernel; old kernel/CPU execution remains unqualified.", "Reference cargo-zigbuild; user's separate builder remains unqualified.", "HTTP/TCP adapters are experimental; full socket server and application integration remain later work."]
        print("E4 PASS: isolated normal/scalar HTTP/TCP and cumulative JSON/SQLite/rustix", flush=True)
        return 0
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        print(f"E4 FAILED: {error}", file=sys.stderr, flush=True)
        return 1
    finally:
        (results / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        for engine, container in reversed(containers):
            command(engine + ["rm", "--force", container], check=False)


if __name__ == "__main__":
    raise SystemExit(main())
