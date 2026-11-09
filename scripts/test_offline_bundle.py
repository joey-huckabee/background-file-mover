"""Package provenance, deterministic archive and cached-license failure checks."""
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("offline_bundle", Path(__file__).with_name("build-offline-bundle.py"))
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


class BundleTests(unittest.TestCase):
    def test_failed_qualification_and_unclean_gates_are_refused(self):
        for report in ({"status": "FAILED"}, {"status": "SCOPED_PASSED", "build_mode": "production"}, {"status": "PASSED", "build_mode": "nfs-qualification"},
                       {"status": "PASSED", "build_mode": "production", "cleanup_error": "still alive"}):
            with self.subTest(report=report), tempfile.TemporaryDirectory() as directory:
                p = Path(directory) / "report.json"
                p.write_text(json.dumps(report), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "clean production gate"):
                    bundle.validated_artifact(p)

    def test_archive_is_deterministic_and_executable_modes_are_explicit(self):
        files = {"README.txt": b"hello\n", "bin/file-mover": b"executable", "verify.sh": b"shell"}
        first = bundle.archive_bytes(files, "example", 123)
        self.assertEqual(first, bundle.archive_bytes(dict(reversed(list(files.items()))), "example", 123))
        with tarfile.open(fileobj=io.BytesIO(first)) as tar:
            self.assertEqual(tar.getmember("example/bin/file-mover").mode, 0o755)
            self.assertEqual(tar.getmember("example/README.txt").mode, 0o644)
            self.assertTrue(all(m.uid == m.gid == 0 and m.mtime == 123 for m in tar.getmembers()))
        for name in ("../escape", "/absolute", "some/../escape", "has space"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                bundle.archive_bytes({name: b"bad"}, "example", 123)

    def test_crate_checksum_and_license_material_are_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "rust").mkdir()
            cache = root / "cache/index"
            cache.mkdir(parents=True)
            report = {"dependencies": [{"name": "example", "version": "1.0.0", "license": "MIT"}]}
            archive = bundle.archive_bytes({"LICENSE": b"license text"}, "example-1.0.0", 123)
            (root / "rust/Cargo.lock").write_text('[[package]]\nname="example"\nversion="1.0.0"\nchecksum="' + bundle.digest(archive) + '"\n')
            with patch.object(bundle, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "missing/corrupt"):
                    bundle.dependency_material(report, root)
                p = cache / "example-1.0.0.crate"
                p.write_bytes(b"corrupt")
                with self.assertRaisesRegex(ValueError, "missing/corrupt"):
                    bundle.dependency_material(report, root)
                p.write_bytes(archive)
                files, inventory = bundle.dependency_material(report, root)
                self.assertEqual(files["share/licenses/crates/example-1.0.0/LICENSE"], b"license text")
                self.assertEqual(inventory[0]["crate_sha256"], bundle.digest(archive))


if __name__ == "__main__":
    unittest.main()
