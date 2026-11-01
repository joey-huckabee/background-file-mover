"""Regression checks for cargo-libc's machine-readable configuration stream."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("sles_gate", Path(__file__).with_name("check-rust-sles.py"))
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


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


if __name__ == "__main__":
    unittest.main()
