#!/usr/bin/env python3
"""Build Rust with cargo-libc, audit every executable, and test in pinned SLES."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tomllib
import uuid

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "scripts/rust-platform.json").read_text())


def prepare_builder(results: Path) -> str:
    """Cache a recipe/config-specific builder; record its actual image and tools."""
    recipe = ROOT / "scripts/Containerfile.rust"
    inputs = recipe.read_bytes() + json.dumps(CONFIG, sort_keys=True).encode()
    image = "localhost/file-mover-cargo-libc:" + hashlib.sha256(inputs).hexdigest()[:20]
    if subprocess.run(["podman", "image", "exists", image], capture_output=True).returncode:
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification", action="store_true", help="Audit/test the retained NFS qualification build")
    options = parser.parse_args()
    mode = "nfs-qualification" if options.qualification else "production"
    features = ["--features", "file-mover/nfs-qualification"] if options.qualification else []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    if options.qualification:
        stamp += "-nfs-qualification"
    results = ROOT / "rust/validation" / stamp
    results.mkdir(parents=True)
    report = {"status": "FAILED", "config": CONFIG, "profiles": {}, "run_id": stamp, "build_mode": mode}
    containers = []
    print(f"SLES validation: {results}", flush=True)
    try:
        builder_image = prepare_builder(results)
        report["builder_recipe_sha256"] = hashlib.sha256((ROOT / "scripts/Containerfile.rust").read_bytes()).hexdigest()
        report["builder_image"] = builder_image
        for role in ("runtime",):
            available = subprocess.run(["podman", "image", "exists", CONFIG[role]], capture_output=True)
            if available.returncode:
                print(f"Pulling pinned {role} image...", flush=True)
                run(["podman", "pull", CONFIG[role]], results / f"{role}-pull.log")
            run(["podman", "image", "inspect", CONFIG[role]], results / f"{role}-image.json")
        registry = "file-mover-cargo-registry"
        for volume in (registry,):
            exists = subprocess.run(["podman", "volume", "inspect", volume], capture_output=True)
            if exists.returncode:
                run(["podman", "volume", "create", volume])
        builder = run(["podman", "create", "--network", "none",
                       "--volume", f"{registry}:/usr/local/cargo/registry",
                       "--env", "LIBSQLITE3_FLAGS=-USQLITE_THREADSAFE -DSQLITE_THREADSAFE=1 -DSQLITE_OMIT_LOAD_EXTENSION -DSQLITE_DQS=0 -USQLITE_DEFAULT_MEMSTATUS -DSQLITE_DEFAULT_MEMSTATUS=0 -DSQLITE_ENABLE_API_ARMOR",
                       "--entrypoint", "/bin/sh", builder_image, "-c", "exec sleep infinity"]).strip()
        containers.append(builder)
        run(["podman", "start", builder])
        archive = results / "source.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for child in (ROOT / "rust").iterdir():
                if child.name not in {"target", "validation"}:
                    tar.add(child, arcname=child.name)
        report["source_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
        run(["podman", "cp", str(archive), f"{builder}:/tmp/source.tar.gz"])
        run(["podman", "exec", builder, "/bin/sh", "-c",
             "mkdir -p /work; tar -xzf /tmp/source.tar.gz -C /work"])
        # Provision locked sources separately; no application build runs online.
        provisioner = run(["podman", "create", "--volume", f"{registry}:/usr/local/cargo/registry",
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
        evidence = json.loads((ROOT / "docs/E5-TOKIO-EVIDENCE.json").read_text())
        integrity = json.loads((ROOT / "scripts/rust-integrity-dependencies.json").read_text())
        expected = evidence["dependencies"] + integrity["dependencies"]
        if sorted((p["name"], p["version"]) for p in dependencies) != sorted((p["name"], p["version"]) for p in expected):
            raise ValueError("dependency graph differs from the pinned E5 plus integrity graph")
        locked = {(p["name"], p["version"]): p.get("checksum") for p in tomllib.loads((ROOT / "rust/Cargo.lock").read_text())["package"]}
        for dependency in integrity["dependencies"]:
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
        run(execute + ["cargo", "clippy", "--config", "/work/cargo-libc.toml", "--offline", "--locked", "--workspace", "--all-targets",
                       "--target", "x86_64-unknown-linux-gnu"] + features + ["--", "-D", "warnings"], results / "clippy.log")
        runtime = run(["podman", "create", "--network", "none", "--cap-drop", "all",
                       "--security-opt", "no-new-privileges", "--entrypoint", "/bin/sh",
                       CONFIG["runtime"], "-c", "exec sleep infinity"]).strip()
        containers.append(runtime)
        run(["podman", "start", runtime])
        runtime_version = run(["podman", "exec", runtime, "getconf", "GNU_LIBC_VERSION"], results / "runtime-glibc.txt").strip()
        if runtime_version != "glibc 2.22":
            raise ValueError(f"wrong runtime glibc: {runtime_version}")
        run(["podman", "exec", runtime, "cat", "/etc/os-release"], results / "runtime-os.txt")
        for profile in ("debug", "release"):
            print(f"Building with cargo-libc and testing {profile} against SLES/glibc 2.22...", flush=True)
            args = execute + ["cargo", "build", "--config", "/work/cargo-libc.toml", "--offline", "--locked", "--workspace",
                              "--all-targets", "--target", "x86_64-unknown-linux-gnu", "--message-format", "json"] + features
            if profile == "release":
                args.append("--release")
            output = run(args, results / f"{profile}-build.log")
            artifacts = {}
            for line in output.splitlines():
                if not line.startswith("{"):
                    continue
                message = json.loads(line)
                if message.get("reason") == "compiler-artifact" and message.get("executable"):
                    artifacts[message["executable"]] = message["profile"]["test"]
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
                if is_test and runtime_service:
                    runtime_exec.insert(-1, "--env")
                    runtime_exec.insert(-1, f"FILE_MOVER_TEST_EXECUTABLE={runtime_service}")
                ldd = run(runtime_exec + ["ldd", "-r", remote], results / f"{name}.ldd")
                if "not found" in ldd or "undefined symbol" in ldd:
                    raise ValueError("runtime relocation/library failure")
                item = {"name": name, "sha256": digest, "test": is_test, "elf": elf_report}
                profile_report["artifacts"].append(item)
                if is_test:
                    test_output = run(runtime_exec + [remote, "--test-threads=1"], results / f"{name}.test")
                    counts = re.findall(r"test result: ok\. (\d+) passed; (\d+) failed", test_output)
                    if not counts or any(int(failed) for _, failed in counts):
                        raise ValueError("missing successful test result")
                    profile_report["tests_passed"] += sum(int(passed) for passed, _ in counts)
                else:
                    smoke = run(runtime_exec + [remote, "--check-platform"], results / f"{name}.smoke")
                    if "file-mover 0.1.0 local-claim prototype" not in smoke:
                        raise ValueError("service runtime smoke failed")
                    if f"build={mode}" not in smoke:
                        raise ValueError("service build-mode label mismatch")
                    runtime_service = remote
            if profile_report["tests_passed"] == 0:
                raise ValueError("no actual tests ran")
        report["status"] = "PASSED"
        print("PASS: debug/release target tests, ELF audit and pinned SLES execution", flush=True)
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
