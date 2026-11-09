"""Regression checks for the cargo-libc gate's configuration and offline safety."""
from contextlib import redirect_stdout, redirect_stderr
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("sles_gate", Path(__file__).with_name("check-rust-sles.py"))
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class DependencyPinTests(unittest.TestCase):
    def test_dependency_pins_are_locked_and_integrity_checksums_match(self):
        root = Path(__file__).resolve().parent.parent
        pins = json.loads((root / "scripts/rust-qualified-dependencies.json").read_text())
        integrity = json.loads((root / "scripts/rust-integrity-dependencies.json").read_text())
        lock = gate.tomllib.loads((root / "rust/Cargo.lock").read_text())
        locked = {(p["name"], p["version"]): p["checksum"] for p in lock["package"] if p.get("source")}
        qualified = [(p["name"], p["version"]) for p in pins["dependencies"] + integrity["dependencies"]]
        self.assertEqual(len(qualified), len(set(qualified)))
        self.assertTrue(set(qualified).issubset(locked))
        for p in integrity["dependencies"]:
            self.assertEqual(p["checksum"], locked[(p["name"], p["version"])])
        self.assertEqual(pins["tokio_selected_features"], sorted(set(pins["tokio_selected_features"])))


class ConfigurationStreamTests(unittest.TestCase):
    def test_provider_diagnostics_do_not_enter_cargo_configuration(self):
        configuration = '[target.x86_64-unknown-linux-gnu]\nrustflags = ["-C", "target-cpu=x86-64"]\n'
        diagnostics = "glibc 2.22 provider (source mode, prepared)\n"
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "provider.log"
            with patch.object(gate.subprocess, "run", return_value=subprocess.CompletedProcess(
                    ["cargo", "libc", "env"], 0, configuration, diagnostics)):
                exported = gate.run(["cargo", "libc", "env"], log, stdout_only=True)
            self.assertEqual(gate.tomllib.loads(exported)["target"]["x86_64-unknown-linux-gnu"]["rustflags"],
                             ["-C", "target-cpu=x86-64"])
            self.assertIn(diagnostics, log.read_text(encoding="utf-8"))

    def test_failed_export_is_not_accepted_even_with_valid_stdout(self):
        with patch.object(gate.subprocess, "run", return_value=subprocess.CompletedProcess(
                ["cargo", "libc", "env"], 1, "[target]\n", "provider verification failed\n")):
            with self.assertRaisesRegex(RuntimeError, "provider verification failed"):
                gate.run(["cargo", "libc", "env"], stdout_only=True)



class TlsNativeCompilerTests(unittest.TestCase):
    def test_target_wrapper_is_required_for_actual_native_sources(self):
        config = ('[env]\n"CC_x86_64-unknown-linux-gnu"="/tools/libc-cc"\n'
                  'CARGO_LIBC_SYSROOT="/old/sysroot"\nCARGO_LIBC_RUN_GLIBC="2.22"\n'
                  'CARGO_LIBC_CC="/tools/clang-16"\n')
        command = '[aws-lc-sys 0.47.0] running: "/tools/libc-cc" "-O2" "-c" "/registry/aws-lc-sys/aws-lc/crypto/a.c"'
        proof = gate.audit_tls_native_build(command, config)
        self.assertEqual(proof['source_compilations'], 1)
        self.assertEqual(proof['sysroot'], '/old/sysroot')
        for bad in ('', command.replace('/tools/libc-cc', '/usr/bin/cc'),
                    command+' "-march=native"', command+' "--sysroot=/new/sysroot"'):
            with self.subTest(command=bad), self.assertRaises(ValueError):
                gate.audit_tls_native_build(bad, config)
        with self.assertRaises(ValueError):
            gate.audit_tls_native_build(command, config.replace('2.22', '2.36'))


class OfflineGateTests(unittest.TestCase):
    def test_missing_cached_inputs_never_fall_back_to_online_provisioning(self):
        for missing in ("builder", "runtime", "registry", "crates", "network"):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "scripts").mkdir()
                (root / "scripts/Containerfile.rust").write_text("FROM pinned\n", encoding="utf-8")
                (root / "rust").mkdir()
                (root / "rust/Cargo.toml").write_text("[workspace]\n", encoding="utf-8")
                commands = []

                def availability(args, **kwargs):
                    if args[1:3] == ["image", "exists"]:
                        role = "runtime" if args[-1] == gate.CONFIG["runtime"] else "builder"
                    else:
                        self.assertEqual(args[1:3], ["volume", "inspect"])
                        role = "registry"
                    return subprocess.CompletedProcess(args, int(role == missing))

                def execute(args, *unused, **kwargs):
                    commands.append(args)
                    if args[1] == "inspect":
                        return "bridge" if missing == "network" else "none"
                    if "fetch" in args:
                        self.assertIn("--offline", args)
                        self.assertIn("--locked", args)
                        raise RuntimeError("offline locked source cache incomplete")
                    return "owned-offline-builder" if args[1] == "create" else ""

                with patch.object(gate, "ROOT", root), patch.object(gate.subprocess, "run", side_effect=availability), \
                        patch.object(gate, "run", side_effect=execute), \
                        patch("sys.argv", ["check-rust-sles.py", "--offline"]), \
                        redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertEqual(gate.main(), 1)
                reports = list((root / "rust/validation").glob("*/report.json"))
                self.assertEqual(len(reports), 1)
                report = json.loads(reports[0].read_text(encoding="utf-8"))
                self.assertEqual(report["status"], "FAILED")
                self.assertTrue(report["offline"])
                self.assertIn("networking" if missing == "network" else "offline", report["error"])
                self.assertNotIn("cleanup_error", report)
                for args in commands:
                    self.assertNotIn(args[1], ("build", "pull"))
                    self.assertNotEqual(args[1:3], ["volume", "create"])
                    if args[1] == "create":
                        self.assertIn("--pull=never", args)
                        self.assertEqual(args[args.index("--network") + 1], "none")
                if missing in ("crates", "network"):
                    self.assertEqual(report["container_networks"], {"builder": "bridge" if missing == "network" else "none"})
                    self.assertEqual(commands[-1], ["podman", "rm", "-f", "owned-offline-builder"])
                else:
                    self.assertFalse(any(args[1] == "create" for args in commands))


if __name__ == "__main__":
    unittest.main()
