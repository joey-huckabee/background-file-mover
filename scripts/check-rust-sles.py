#!/usr/bin/env python3
"""Build Rust with cargo-libc, audit every executable, and test in pinned SLES."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import tarfile
import tomllib
import uuid

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "scripts/rust-platform.json").read_text())


def prepare_builder(results: Path, *, offline: bool = False) -> str:
    """Cache a recipe/config-specific builder; record its actual image and tools."""
    recipe = ROOT / "scripts/Containerfile.rust"
    inputs = recipe.read_bytes() + json.dumps(CONFIG, sort_keys=True).encode()
    image = "localhost/file-mover-cargo-libc:" + hashlib.sha256(inputs).hexdigest()[:20]
    if subprocess.run(["podman", "image", "exists", image], capture_output=True).returncode:
        if offline:
            raise RuntimeError("offline prerequisite missing: cached cargo-libc builder; run the gate without --offline on a connected build host first")
        print("Preparing cargo-libc builder (first run may take several minutes)...", flush=True)
        run(["podman", "build", "--jobs", "1", "--tag", image,
             "--build-arg", f"RUST_IMAGE={CONFIG['builder_base']}",
             "--build-arg", f"CARGO_LIBC_VERSION={CONFIG['cargo_libc']}",
             "--file", str(recipe), str(ROOT / "scripts")], results / "builder-build.log", timeout=1800)
    run(["podman", "image", "inspect", image], results / "builder-image.json")
    return image


def run(args: list[str], log: Path | None = None, timeout: int = 900, *, stdout_only: bool = False) -> str:
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=timeout)
    output = result.stdout + result.stderr
    if log:
        log.write_text(output, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {args[0:3]}\n{output[-4000:]}")
    return result.stdout if stdout_only else output


def audit(text: str) -> dict:
    if not re.search(r"Machine:\s+Advanced Micro Devices X86-64", text):
        raise ValueError("wrong ELF architecture")
    loader = re.search(r"Requesting program interpreter: ([^\]]+)", text)
    if not loader or loader[1] != CONFIG["interpreter"]:
        raise ValueError("wrong ELF interpreter")
    if re.search(r"\((?:RPATH|RUNPATH)\)", text):
        raise ValueError("unexpected runtime library search path")
    libraries = sorted(set(re.findall(r"\(NEEDED\).*Shared library: \[([^\]]+)\]", text)))
    if not libraries or set(libraries) - set(CONFIG["allowed_libraries"]):
        raise ValueError(f"unexpected shared libraries: {libraries}")
    imports = sorted(set(re.findall(r"\bUND\s+(\S+)", text)))
    versions = sorted(set(re.findall(r"@((?:GLIBC|GCC)_[\w.]+)", "\n".join(imports))))
    glibc = []
    for version in versions:
        if version.startswith("GLIBC_"):
            if not re.fullmatch(r"GLIBC_\d+(?:\.\d+)+", version):
                raise ValueError(f"private/unrecognized glibc version: {version}")
            if tuple(map(int, version[6:].split("."))) > (2, 22):
                raise ValueError(f"unsupported glibc version: {version}")
            glibc.append(version)
    if not glibc:
        raise ValueError("no auditable glibc imports")
    if any(symbol.split("@")[0] == "renameat2" for symbol in imports):
        raise ValueError("new glibc renameat2 wrapper")
    return {"interpreter": loader[1], "libraries": libraries, "versions": versions,
            "maximum_glibc": max(glibc, key=lambda v: tuple(map(int, v[6:].split("."))))}


def negative_controls(text: str) -> list[str]:
    glibc = re.search(r"@GLIBC_\d+(?:\.\d+)+", text)
    if not glibc:
        raise ValueError("missing symbol for audit controls")
    cases = {
        "new-glibc": text.replace(glibc[0], "@GLIBC_2.23"),
        "private-glibc": text.replace(glibc[0], "@GLIBC_PRIVATE"),
        "wrong-loader": text.replace(CONFIG["interpreter"], "/lib/ld-musl-x86_64.so.1"),
        "unexpected-library": text + "\n (NEEDED) Shared library: [libsqlite3.so.0]\n",
        "runpath": text + "\n (RUNPATH) Library runpath: [/modern/lib]\n",
        "wrong-architecture": text.replace("Advanced Micro Devices X86-64", "AArch64"),
    }
    for name, invalid in cases.items():
        try:
            audit(invalid)
        except ValueError:
            continue
        raise ValueError(f"ELF audit accepted negative control: {name}")
    return list(cases)



def audit_tls_native_build(text: str, configuration: str) -> dict:
    """Prove AWS-LC C/assembly went through the selected glibc-2.22 wrapper."""
    environment = tomllib.loads(configuration)["env"]
    wrapper = environment["CC_x86_64-unknown-linux-gnu"]
    sysroot = environment["CARGO_LIBC_SYSROOT"]
    if Path(wrapper).name != "libc-cc" or environment["CARGO_LIBC_RUN_GLIBC"] != "2.22":
        raise ValueError("TLS native compiler/provider is not the glibc2.22 wrapper")
    commands = []
    for line in text.splitlines():
        match = re.match(r"^\[aws-lc-sys [^\]]+\] running: (.+)$", line)
        if not match:
            continue
        arguments = shlex.split(match[1])
        if "-c" not in arguments or not any("/aws-lc/" in a and a.endswith((".c", ".S", ".s", ".cc", ".cpp", ".cxx")) for a in arguments):
            continue
        cpp = any("/aws-lc/" in a and a.endswith((".cc", ".cpp", ".cxx")) for a in arguments)
        selected_wrapper = environment["CXX_x86_64-unknown-linux-gnu"] if cpp else wrapper
        if Path(selected_wrapper).name != ("libc-cxx" if cpp else "libc-cc") or arguments[0] != selected_wrapper:
            raise ValueError("TLS native source bypassed cargo-libc compiler wrapper")
        if any(a in ("-march=native", "-mcpu=native", "-mtune=native") for a in arguments):
            raise ValueError("TLS native source selected the build host CPU")
        if any(a.startswith("--sysroot=") and a != "--sysroot=" + sysroot for a in arguments):
            raise ValueError("TLS native source overrides the selected sysroot")
        commands.append(arguments)
    if not commands:
        raise ValueError("no auditable AWS-LC target compiler commands")
    return {"source_compilations": len(commands), "wrapper": wrapper,
            "compiler": environment["CARGO_LIBC_CC"], "sysroot": sysroot, "glibc": "2.22"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification", action="store_true", help="Audit/test the retained NFS qualification build")
    parser.add_argument("--offline", action="store_true", help="Use cached images and locked sources only; never build/pull images or provision online")
    parser.add_argument("--tls-proof-only", action="store_true", help="Scoped TLS/app smoke only; report is SCOPED_PASSED, never a full qualification")
    options = parser.parse_args()
    mode = "nfs-qualification" if options.qualification else "production"
    features = ["--features", "file-mover/nfs-qualification"] if options.qualification else []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    if options.qualification:
        stamp += "-nfs-qualification"
    results = ROOT / "rust/validation" / stamp
    results.mkdir(parents=True)
    report = {"status": "FAILED", "config": CONFIG, "profiles": {}, "run_id": stamp, "build_mode": mode,
              "offline": options.offline}
    report["test_scope"] = "tls-proof-only" if options.tls_proof_only else "full"
    containers = []
    print(f"SLES validation: {results}", flush=True)
    try:
        builder_image = prepare_builder(results, offline=options.offline)
        report["builder_recipe_sha256"] = hashlib.sha256((ROOT / "scripts/Containerfile.rust").read_bytes()).hexdigest()
        report["builder_image"] = builder_image
        for role in ("runtime",):
            available = subprocess.run(["podman", "image", "exists", CONFIG[role]], capture_output=True)
            if available.returncode:
                if options.offline:
                    raise RuntimeError(f"offline prerequisite missing: pinned {role} image; run the gate without --offline on a connected build host first")
                print(f"Pulling pinned {role} image...", flush=True)
                run(["podman", "pull", CONFIG[role]], results / f"{role}-pull.log")
            run(["podman", "image", "inspect", CONFIG[role]], results / f"{role}-image.json")
        registry = "file-mover-cargo-registry"
        for volume in (registry,):
            exists = subprocess.run(["podman", "volume", "inspect", volume], capture_output=True)
            if exists.returncode:
                if options.offline:
                    raise RuntimeError("offline prerequisite missing: file-mover-cargo-registry source cache; run the gate without --offline on a connected build host first")
                run(["podman", "volume", "create", volume])
        builder = run(["podman", "create", "--pull=never", "--network", "none",
                       "--volume", f"{registry}:/usr/local/cargo/registry",
                       "--env", "AWS_LC_SYS_STATIC=1", "--env", "AWS_LC_SYS_CMAKE_BUILDER=0",
                       "--env", "CC_ENABLE_DEBUG_OUTPUT=1",
                       "--env", "LIBSQLITE3_FLAGS=-USQLITE_THREADSAFE -DSQLITE_THREADSAFE=1 -DSQLITE_OMIT_LOAD_EXTENSION -DSQLITE_DQS=0 -USQLITE_DEFAULT_MEMSTATUS -DSQLITE_DEFAULT_MEMSTATUS=0 -DSQLITE_ENABLE_API_ARMOR",
                       "--entrypoint", "/bin/sh", builder_image, "-c", "exec sleep infinity"]).strip()
        containers.append(builder)
        run(["podman", "start", builder])
        report["container_networks"] = {"builder": run(["podman", "inspect", "--format", "{{.HostConfig.NetworkMode}}", builder]).strip()}
        if report["container_networks"]["builder"] != "none":
            raise ValueError("builder networking is not disabled")
        archive = results / "source.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for child in (ROOT / "rust").iterdir():
                if child.name not in {"target", "validation"}:
                    tar.add(child, arcname=child.name)
        report["source_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
        run(["podman", "cp", str(archive), f"{builder}:/tmp/source.tar.gz"])
        run(["podman", "exec", builder, "/bin/sh", "-c",
             "mkdir -p /work; tar -xzf /tmp/source.tar.gz -C /work"])
        if options.offline:
            print("Checking cached locked sources without networking...", flush=True)
            run(["podman", "exec", "--workdir", "/work", builder, "cargo", "fetch", "--offline", "--locked"], results / "fetch.log")
        else:
            # Provision locked sources separately; no application build runs online.
            provisioner = run(["podman", "create", "--pull=never", "--volume", f"{registry}:/usr/local/cargo/registry",
                               "--entrypoint", "/bin/sh", builder_image, "-c", "exec sleep infinity"]).strip()
            containers.append(provisioner)
            run(["podman", "start", provisioner])
            run(["podman", "cp", str(archive), f"{provisioner}:/tmp/source.tar.gz"])
            run(["podman", "exec", provisioner, "/bin/sh", "-c", "mkdir -p /work; tar -xzf /tmp/source.tar.gz -C /work"])
            print("Provisioning the locked E1–E5 dependency graph...", flush=True)
            run(["podman", "exec", "--workdir", "/work", provisioner, "cargo", "fetch", "--locked"], results / "fetch.log")
        tools = run(["podman", "exec", "--workdir", "/work", builder, "/bin/sh", "-c",
                     "rustc --version; cargo --version; cargo libc --version; clang-16 --version; gcc --version; ld.bfd --version"], results / "toolchain.txt")
        if f"rustc {CONFIG['rust']} " not in tools or f"cargo-libc {CONFIG['cargo_libc']}" not in tools.splitlines():
            raise ValueError("unexpected Rust/cargo-libc version")
        run(["podman", "exec", builder, "dpkg-query", "-W"], results / "builder-packages.txt")
        execute = ["podman", "exec", "--workdir", "/work", builder]
        # Export the documented Cargo configuration: preserve JSON discovery of
        # every executable, while keeping host build scripts/proc macros native.
        selection = ["--target", CONFIG["target"], "--provider-mode", CONFIG["provider_mode"], "--cc", CONFIG["cc"]]
        configuration = run(execute + ["cargo", "libc", "env"] + selection + ["--format", "cargo"],
                            results / "provider-prepare.log", stdout_only=True)
        tomllib.loads(configuration)  # Refuse diagnostics accidentally mixed into the configuration.
        (results / "cargo-libc.toml").write_text(configuration, encoding="utf-8")
        run(["podman", "cp", str(results / "cargo-libc.toml"), f"{builder}:/work/cargo-libc.toml"])
        run(execute + ["cargo", "libc", "provider", "verify", "--glibc", "2.22", "--mode", CONFIG["provider_mode"]], results / "provider-verify.log")
        metadata = json.loads(run(execute + ["cargo", "metadata", "--offline", "--locked", "--format-version", "1",
                                             "--filter-platform", "x86_64-unknown-linux-gnu"] + features, results / "metadata.json"))
        dependencies = [package for package in metadata["packages"] if package["source"]]
        dependency_pins = (ROOT / "scripts/rust-qualified-dependencies.json").read_bytes()
        report["dependency_pins_sha256"] = hashlib.sha256(dependency_pins).hexdigest()
        evidence = json.loads(dependency_pins)
        integrity = json.loads((ROOT / "scripts/rust-integrity-dependencies.json").read_text())
        expected = evidence["dependencies"] + integrity["dependencies"]
        if sorted((p["name"], p["version"]) for p in dependencies) != sorted((p["name"], p["version"]) for p in expected):
            raise ValueError("dependency graph differs from the pinned qualified plus integrity graph")
        locked = {(p["name"], p["version"]): p.get("checksum") for p in tomllib.loads((ROOT / "rust/Cargo.lock").read_text())["package"]}
        for dependency in integrity["dependencies"] + [p for p in evidence["dependencies"] if "checksum" in p]:
            if locked[(dependency["name"], dependency["version"])] != dependency["checksum"]:
                raise ValueError("integrity dependency checksum changed")
        qualified_features = {
            "rusqlite": ["bundled", "modern_sqlite"],
            "rustix": ["alloc", "fs", "net", "process", "std"],
            "linux-raw-sys": ["auxvec", "elf", "errno", "general", "if_ether", "ioctl", "net", "netlink", "no_std", "prctl", "xdp"],
            "tokio": sorted(evidence["tokio_selected_features"]),
            "serde": ["derive", "serde_derive", "std"],
            "serde_json": ["std"],
            "httparse": ["std"],
            "sha2": integrity["sha2_features"],
        }
        qualified_features.update(evidence["tls_selected_features"])
        nodes = {node["id"]: node for node in metadata["resolve"]["nodes"]}
        report["workspace_features"] = {}
        for package in metadata["packages"]:
            if package["name"] in ("file-mover", "mover-fs"):
                selected = sorted(nodes[package["id"]]["features"])
                expected_features = ["default", "nfs-qualification"] if options.qualification else ["default"]
                if selected != expected_features:
                    raise ValueError(f"wrong build capability for {package['name']}: {selected}")
                report["workspace_features"][package["name"]] = selected
        for package in dependencies:
            if package["name"] in qualified_features:
                if sorted(nodes[package["id"]]["features"]) != qualified_features[package["name"]]:
                    raise ValueError(f"unqualified features for {package['name']}")
        report["dependencies"] = [{"name": p["name"], "version": p["version"], "license": p["license"]} for p in dependencies]
        run(execute + ["cargo", "fmt", "--all", "--", "--check"], results / "fmt.log")
        clippy_output = run(execute + ["cargo", "clippy", "-vv", "--config", "/work/cargo-libc.toml", "--offline", "--locked", "--workspace", "--all-targets",
                       "--target", "x86_64-unknown-linux-gnu"] + features + ["--", "-D", "warnings"], results / "clippy.log")
        report["tls_native_compiler_audits"] = {"clippy_debug": audit_tls_native_build(clippy_output, configuration)}
        runtime = run(["podman", "create", "--pull=never", "--network", "none", "--cap-drop", "all",
                       "--security-opt", "no-new-privileges", "--entrypoint", "/bin/sh",
                       CONFIG["runtime"], "-c", "exec sleep infinity"]).strip()
        containers.append(runtime)
        run(["podman", "start", runtime])
        report["container_networks"]["runtime"] = run(["podman", "inspect", "--format", "{{.HostConfig.NetworkMode}}", runtime]).strip()
        if report["container_networks"]["runtime"] != "none":
            raise ValueError("runtime networking is not disabled")
        runtime_version = run(["podman", "exec", runtime, "getconf", "GNU_LIBC_VERSION"], results / "runtime-glibc.txt").strip()
        if runtime_version != "glibc 2.22":
            raise ValueError(f"wrong runtime glibc: {runtime_version}")
        run(["podman", "exec", runtime, "cat", "/etc/os-release"], results / "runtime-os.txt")
        # Older OCI exec implementations can inherit a process group outside
        # this PID namespace (getpgrp() == 0). Give target processes a visible
        # session/group; --wait preserves a forked program's actual exit status.
        session = run(["podman", "exec", "--user", "1000:1000", runtime,
                       "/usr/bin/setsid", "--wait", "/bin/sh", "-c",
                       "exec ps -o pid= -o pgid= -o sid= -p $$"], results / "runtime-session.txt").split()
        if len(session) != 3 or len(set(session)) != 1 or int(session[0]) <= 0:
            raise ValueError(f"target session/process group is not private and visible: {session}")
        report["runtime_session"] = dict(zip(("pid", "pgid", "sid"), map(int, session)))
        # Fresh disposable credentials never enter the source archive/binary/bundle.
        fixture_helper = ROOT / "scripts/tls_proof_fixture.py"
        report["tls_fixture_helper_sha256"] = hashlib.sha256(fixture_helper.read_bytes()).hexdigest()
        run(["podman", "cp", str(fixture_helper), f"{builder}:/tmp/tls_proof_fixture.py"])
        fixture_inventory = json.loads(run(execute + ["python3", "/tmp/tls_proof_fixture.py",
            "--output", "/tmp/tls-proof-der", "--archive", "/tmp/tls-proof.tar"], results / "tls-fixture.log"))
        with tempfile.TemporaryDirectory(prefix="file-mover-tls-gate-") as temporary:
            fixture_archive = Path(temporary) / "proof.tar"
            run(["podman", "cp", f"{builder}:/tmp/tls-proof.tar", str(fixture_archive)])
            copied = subprocess.run(["podman", "cp", "--archive=false", "-", f"{runtime}:/tmp"],
                input=fixture_archive.read_bytes(), capture_output=True, timeout=60)
            if copied.returncode:
                raise RuntimeError("TLS fixture archive transfer failed")
        fixture_root = "/tmp/file-mover-tls-proof"
        custody = run(["podman", "exec", "--user", "1000:1000", runtime, "stat", "-c", "%u:%g:%a",
                       fixture_root + "/server.key.der"]).strip()
        if custody != "1000:1000:600":
            raise ValueError("TLS fixture private-key custody differs from intended numeric owner/mode")
        public_names = sorted(fixture_inventory["certificates"])
        received = run(["podman", "exec", "--user", "1000:1000", runtime, "sha256sum"] +
                       [fixture_root + "/" + name for name in public_names])
        actual_certificates = {Path(line.split()[1]).name: line.split()[0] for line in received.splitlines()}
        if actual_certificates != {name: row["sha256"] for name, row in fixture_inventory["certificates"].items()}:
            raise ValueError("TLS fixture certificate transfer hash mismatch")
        report["tls_fixture"] = fixture_inventory | {"private_archive_retained": False, "key_custody": custody}
        report["native_tls_build"] = {"AWS_LC_SYS_STATIC": "1", "AWS_LC_SYS_CMAKE_BUILDER": "0",
                                      "CC_ENABLE_DEBUG_OUTPUT": "1", "target_cc": CONFIG["cc"]}
        for profile in ("debug", "release"):
            print(f"Building with cargo-libc and testing {profile} against SLES/glibc 2.22...", flush=True)
            args = execute + ["cargo", "build", "-vv", "--config", "/work/cargo-libc.toml", "--offline", "--locked", "--workspace",
                              "--all-targets", "--target", "x86_64-unknown-linux-gnu", "--message-format", "json"] + features
            if profile == "release":
                args.append("--release")
            output = run(args, results / f"{profile}-build.log")
            if profile == "release":
                report["tls_native_compiler_audits"]["release"] = audit_tls_native_build(output, configuration)
            artifacts = {}
            for line in output.splitlines():
                if not line.startswith("{"):
                    continue
                message = json.loads(line)
                if message.get("reason") == "compiler-artifact" and message.get("executable"):
                    artifacts[message["executable"]] = message["profile"]["test"]
            if options.tls_proof_only:
                artifacts = {p: test for p, test in artifacts.items() if not test or Path(p).name.startswith("tls-")}
            if not artifacts or not any(artifacts.values()):
                raise ValueError("no target test executables discovered")
            profile_report = {"artifacts": [], "tests_passed": 0}
            report["profiles"][profile] = profile_report
            runtime_service = None
            for index, (path, is_test) in enumerate(sorted(artifacts.items(), key=lambda item: (item[1], item[0]))):
                if not path.startswith("/work/target/x86_64-unknown-linux-gnu/"):
                    raise ValueError(f"unexpected artifact location: {path}")
                name = f"{profile}-{index}-{Path(path).name}"
                if options.qualification:
                    name += "-nfs-qualification"
                local = results / name
                run(execute + ["cargo", "libc", "inspect", path, "--max-glibc", "2.22", "--json"], results / f"{name}.cargo-libc.json")
                elf_text = run(execute + ["readelf", "-W", "-h", "-l", "-d", "--dyn-syms", path], results / f"{name}.elf")
                elf_report = audit(elf_text)
                if "audit_negative_controls" not in report:
                    report["audit_negative_controls"] = negative_controls(elf_text)
                run(["podman", "cp", f"{builder}:{path}", str(local)])
                digest = hashlib.sha256(local.read_bytes()).hexdigest()
                remote = f"/tmp/{name}"
                run(["podman", "cp", str(local), f"{runtime}:{remote}"])
                run(["podman", "exec", runtime, "chmod", "0555", remote])
                received = run(["podman", "exec", runtime, "sha256sum", remote]).split()[0]
                if received != digest:
                    raise ValueError("runtime artifact hash mismatch")
                runtime_exec = ["podman", "exec", "--user", "1000:1000", "--env", "LD_BIND_NOW=1", runtime]
                if is_test and Path(path).name.startswith("tls-"):
                    runtime_exec.insert(-1, "--env")
                    runtime_exec.insert(-1, f"FILE_MOVER_TLS_FIXTURES={fixture_root}")
                if is_test and runtime_service:
                    runtime_exec.insert(-1, "--env")
                    runtime_exec.insert(-1, f"FILE_MOVER_TEST_EXECUTABLE={runtime_service}")
                ldd = run(runtime_exec + ["ldd", "-r", remote], results / f"{name}.ldd")
                if "not found" in ldd or "undefined symbol" in ldd:
                    raise ValueError("runtime relocation/library failure")
                item = {"name": name, "sha256": digest, "test": is_test, "elf": elf_report}
                profile_report["artifacts"].append(item)
                if is_test:
                    # Qualification API cases include bounded fault/backoff waits.
                    # With 103 cases, measured local production + qualification-only
                    # waits exceed the old 900s whole-process ceiling. Individual
                    # test/runtime deadlines stay unchanged; run every assertion.
                    test_timeout = 1200 if options.qualification and Path(path).name.startswith("api-") else 900
                    if test_timeout != 900:
                        profile_report["api_suite_timeout_seconds"] = test_timeout
                    test_output = run(runtime_exec + ["/usr/bin/setsid", "--wait", remote, "--test-threads=1"], results / f"{name}.test", timeout=test_timeout)
                    counts = re.findall(r"test result: ok\. (\d+) passed; (\d+) failed", test_output)
                    if not counts or any(int(failed) for _, failed in counts):
                        raise ValueError("missing successful test result")
                    profile_report["tests_passed"] += sum(int(passed) for passed, _ in counts)
                else:
                    smoke = run(runtime_exec + ["/usr/bin/setsid", "--wait", remote, "--check-platform"], results / f"{name}.smoke")
                    if "file-mover 0.1.0 local-claim prototype" not in smoke:
                        raise ValueError("service runtime smoke failed")
                    if f"build={mode}" not in smoke:
                        raise ValueError("service build-mode label mismatch")
                    runtime_service = remote
            if profile_report["tests_passed"] == 0:
                raise ValueError("no actual tests ran")
        report["status"] = "SCOPED_PASSED" if options.tls_proof_only else "PASSED"
        print(report["status"] + ": debug/release target tests, ELF audit and pinned SLES execution", flush=True)
        return 0
    except Exception as error:
        report["error"] = str(error)
        print(str(error), file=sys.stderr)
        return 1
    finally:
        for container in reversed(containers):
            try:
                run(["podman", "rm", "-f", container], timeout=60)
            except Exception as error:
                report["cleanup_error"] = str(error)
        (results / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
