#!/usr/bin/env python3
"""Package an exact SLES-gated production release executable, without downloads."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parent.parent


def command(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validated_artifact(report_path: Path) -> tuple[dict, bytes, bytes]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    config = json.loads((ROOT / "scripts/rust-platform.json").read_text(encoding="utf-8"))
    if report.get("status") != "PASSED" or report.get("cleanup_error") or report.get("build_mode") != "production":
        raise ValueError("require a passed, clean production gate; qualification executables cannot ship")
    if report["config"] != config:
        raise ValueError("gate toolchain/runtime pins differ from current pins")
    if set(report.get("audit_negative_controls", [])) != {"new-glibc", "private-glibc", "wrong-loader", "unexpected-library", "runpath", "wrong-architecture"}:
        raise ValueError("gate audit controls are incomplete")
    for profile in ("debug", "release"):
        if report["profiles"][profile]["tests_passed"] <= 0:
            raise ValueError("gate has no target tests")
        for artifact in report["profiles"][profile]["artifacts"]:
            name = artifact["name"]
            if Path(name).name != name or name in (".", ".."):
                raise ValueError("unsafe gate artifact name")
            if digest((report_path.parent / name).read_bytes()) != artifact["sha256"]:
                raise ValueError("gate artifact hash mismatch: " + name)
    selected = [a for a in report["profiles"]["release"]["artifacts"] if not a["test"]]
    if len(selected) != 1 or "nfs-qualification" in selected[0]["name"]:
        raise ValueError("expected exactly one production release executable")
    source = (report_path.parent / "source.tar.gz").read_bytes()
    if digest(source) != report["source_sha256"]:
        raise ValueError("gate source archive hash mismatch")
    with tarfile.open(fileobj=io.BytesIO(source)) as tar:
        actual = {m.name: digest(tar.extractfile(m).read()) for m in tar.getmembers() if m.isfile()}
        if any(not (m.isfile() or m.isdir()) for m in tar.getmembers()):
            raise ValueError("gate source contains nonregular members")
    names = command("git", "ls-files", "rust").splitlines()
    expected = {name[5:]: digest(subprocess.check_output(["git", "show", "HEAD:" + name], cwd=ROOT)) for name in names}
    if command("git", "status", "--porcelain", "--", "rust") or actual != expected:
        raise ValueError("gate source does not match clean committed Rust inputs; run fresh gates")
    return report, (report_path.parent / selected[0]["name"]).read_bytes(), source


def dependency_material(report: dict, registry: Path) -> tuple[dict[str, bytes], list[dict]]:
    locked = tomllib.loads((ROOT / "rust/Cargo.lock").read_text(encoding="utf-8"))
    checksums = {(p["name"], p["version"]): p.get("checksum") for p in locked["package"]}
    files: dict[str, bytes] = {}
    inventory = []
    for package in sorted(report["dependencies"], key=lambda p: p["name"]):
        name = f"{package['name']}-{package['version']}"
        candidates = list((registry / "cache").glob(f"*/{name}.crate"))
        expected = checksums[(package["name"], package["version"])]
        matches = [p.read_bytes() for p in candidates if digest(p.read_bytes()) == expected]
        if not matches:
            raise ValueError("locked crate archive missing/corrupt: " + name)
        archive = matches[0]
        files[f"sources/crates/{name}.crate"] = archive
        notices = []
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for member in tar.getmembers():
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != name:
                    raise ValueError("unsafe crate archive path")
                if member.isfile() and path.name.lower().startswith(("license", "copying", "notice", "copyright")):
                    relative = str(PurePosixPath(*path.parts[1:]))
                    target = f"share/licenses/crates/{name}/{relative}"
                    if not re.fullmatch(r"[A-Za-z0-9_./+-]+", target):
                        raise ValueError("unsupported notice path: " + target)
                    files[target] = tar.extractfile(member).read()
                    notices.append(target)
        if not notices:
            raise ValueError("no license/notice material found for " + name)
        inventory.append({**package, "crate_sha256": expected, "notices": sorted(notices)})
    return files, inventory


def rust_notices(report_path: Path, report: dict) -> dict[str, bytes]:
    image = report["builder_image"]
    expected = json.loads((report_path.parent / "builder-image.json").read_text())[0]["Id"]
    actual = json.loads(command("podman", "image", "inspect", image))[0]["Id"]
    if actual != expected:
        raise ValueError("cached builder image differs from gate evidence")
    owned = command("podman", "create", "--pull=never", "--network", "none", "--entrypoint", "/bin/sh", image, "-c", "exec sleep infinity")
    try:
        command("podman", "start", owned)
        sysroot = command("podman", "exec", owned, "rustc", "--print", "sysroot")
        files = {}
        with tempfile.TemporaryDirectory() as directory:
            for name in ("COPYRIGHT", "LICENSE-APACHE", "LICENSE-MIT"):
                target = Path(directory) / name
                command("podman", "cp", f"{owned}:{sysroot}/share/doc/rust/{name}", str(target))
                files[f"share/licenses/rust-toolchain/{name}"] = target.read_bytes()
        return files
    finally:
        command("podman", "rm", "-f", owned)


def archive_bytes(files: dict[str, bytes], name: str, epoch: int) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0, filename="") as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for relative, data in sorted(files.items()):
                path = PurePosixPath(relative)
                if path.is_absolute() or ".." in path.parts or not re.fullmatch(r"[A-Za-z0-9_./+-]+", relative):
                    raise ValueError("unsafe bundle path")
                member = tarfile.TarInfo(f"{name}/{relative}")
                member.size = len(data)
                member.uid = member.gid = 0
                member.uname = member.gname = "root"
                member.mtime = epoch
                member.mode = 0o755 if relative in ("bin/file-mover", "install.sh", "verify.sh") else 0o644
                tar.addfile(member, io.BytesIO(data))
    return buffer.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate-report", required=True, type=Path)
    parser.add_argument("--registry", type=Path, help="existing Cargo registry cache; default: prepared Podman volume")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "rust/validation/bundles")
    args = parser.parse_args()
    if command("git", "status", "--porcelain"):
        raise ValueError("commit bundle tooling/documentation first; packaging requires a clean checkout")
    report_path = args.gate_report.resolve(strict=True)
    report, executable, source = validated_artifact(report_path)
    registry = args.registry or Path(command("podman", "volume", "inspect", "file-mover-cargo-registry", "--format", "{{.Mountpoint}}"))
    files, dependencies = dependency_material(report, registry)
    files.update(rust_notices(report_path, report))
    files.update({"bin/file-mover": executable, "sources/rust-source.tar.gz": source,
                  "share/licenses/file-mover/LICENSE": (ROOT / "LICENSE").read_bytes(),
                  "evidence/gate-report.json": report_path.read_bytes()})
    for name in ("install.sh", "verify.sh"):
        files[name] = (ROOT / "scripts/bundle" / name).read_bytes().replace(b"\r\n", b"\n")
    files["systemd/file-mover.service.in"] = (ROOT / "scripts/bundle/file-mover.service.in").read_bytes().replace(b"\r\n", b"\n")
    config = (ROOT / "rust/config/local.example.json").read_bytes().replace(b"\r\n", b"\n")
    files["config/local.example.json"] = config
    for role in ("source", "destination"):
        files[f"config/{role}-binding.example.json"] = json.dumps(json.loads(config)[role + "_binding"], separators=(",", ":")).encode()
    # Offline docs plus complete tracked project source for code references.
    # Ignored historical raw validation packs are deliberately not imported.
    for path in command("git", "ls-files", "docs", "README.md", "CONVERSATION.md", "CHANGELOG.md").splitlines():
        if Path(path).suffix in (".md", ".json", ".tsv"):
            files["share/doc/" + path] = subprocess.check_output(["git", "show", "HEAD:" + path], cwd=ROOT)
    project = subprocess.check_output(["git", "archive", "--format=tar", "HEAD"], cwd=ROOT)
    files["sources/project-source.tar.gz"] = gzip.compress(project, mtime=0)
    commit = command("git", "rev-parse", "HEAD")
    version = tomllib.loads((ROOT / "rust/Cargo.toml").read_text())["workspace"]["package"]["version"]
    name = f"file-mover-{version}-prototype-{commit[:12]}-linux-x86_64"
    metadata = {"format": 1, "name": name, "packaging_commit": commit, "rust_tree": command("git", "rev-parse", "HEAD:rust"),
                "gate_run": report["run_id"], "gate_report_sha256": digest(report_path.read_bytes()),
                "executable_sha256": digest(executable), "target": report["config"]["target"],
                "required_os_libraries": next(a["elf"]["libraries"] for a in report["profiles"]["release"]["artifacts"] if not a["test"]),
                "dependencies": dependencies, "scope": "native local-filesystem prototype; no production NFS, remote ingress or qualified shipping systemd policy"}
    files["bundle.json"] = (json.dumps(metadata, indent=2) + "\n").encode()
    files["README.txt"] = b"Verify the external archive SHA256 from a trusted channel before extraction.\nThen run: sh verify.sh\nInstall to a new absolute directory: sh install.sh /opt/file-mover/NEW-VERSION\nRead share/doc/docs/OFFLINE-INSTALL.md before configuration or activation.\nNo service/state/configuration is changed automatically. Prototype, not a production release.\n"
    files["SHA256SUMS"] = "".join(f"{digest(data)}  ./{path}\n" for path, data in sorted(files.items())).encode()
    archive = archive_bytes(files, name, int(command("git", "show", "-s", "--format=%ct", "HEAD")))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / (name + ".tar.gz")
    with output.open("xb") as handle:
        handle.write(archive)
    with output.with_suffix(output.suffix + ".sha256").open("x", encoding="utf-8") as handle:
        handle.write(f"{digest(archive)}  {output.name}\n")
    print(output)
    print("SHA256 " + digest(archive))
    print(f"{len(files)} files; {len(dependencies)} locked crate source/license records; no downloads")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
