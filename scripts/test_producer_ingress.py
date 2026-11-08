"""Portable checker tests; no container, Rust build, or claim of UID isolation."""
import base64
import copy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tarfile
import tempfile
import threading
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('producer_ingress_checker', Path(__file__).with_name('check-producer-ingress.py'))
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


def reply(code=200, body=None):
    data = json.dumps({} if body is None else body).encode()
    return f'HTTP/1.1 {code} Result\r\nContent-Length: {len(data)}\r\nConnection: close\r\n\r\n'.encode()+data


class Portable(unittest.TestCase):
    def test_request_keeps_duplicate_headers_and_utf8_content_length(self):
        body = {'path': '\u2028é'}
        raw = CHECK.wire(body=body, headers=[(CHECK.PRINCIPAL, 'fixture')]*2)
        head, data = raw.split(b'\r\n\r\n')
        self.assertEqual(json.loads(data), body)
        self.assertEqual(head.count(b'X-File-Mover-Generator:'), 2)
        self.assertIn(b'Content-Length: '+str(len(data)).encode(), head)
        self.assertIn(b'Host: localhost\r\n', raw)
        self.assertIn('Host: localhost', CHECK.CAPACITY_COMMON)

    def test_reply_requires_full_single_framed_body(self):
        self.assertEqual(CHECK.parse_reply(reply())['code'], 200)
        for bad in (reply()[:-1], reply()+b'extra', reply().replace(b'Content-Length:', b'Content-Length: 2\r\nContent-Length:'),
                    reply().replace(b'\r\n', b'\n')):
            with self.subTest(raw=bad), self.assertRaises((AssertionError, ValueError)):
                CHECK.parse_reply(bad)

    def test_operator_transport_close_is_recorded_without_fabricating_json(self):
        runner = CHECK.Runner({'requests': []})
        result = subprocess.CompletedProcess([], 0, stdout=b'', stderr=b'')
        with patch.object(runner, 'execute', return_value=result):
            row = runner.http('/fixture/operator.sock', CHECK.wire('GET', '/healthz'))
        self.assertEqual(row['raw_base64'], '')
        self.assertNotIn('code', row)
        self.assertNotIn('body', row)

    def test_refusal_envelope_and_permanent_retry_semantics(self):
        row = dict(code=403, body=dict(recording_id=None, error='caller_not_authorized',
                   retryable=False, retry_after_seconds=None, source_paths_released=False))
        CHECK.error_reply(row, 403, {'caller_not_authorized'})
        for field, value in (('source_paths_released', True), ('retryable', True), ('job_id', '1')):
            bad = copy.deepcopy(row)
            bad['body'][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                CHECK.error_reply(bad, 403, {'caller_not_authorized'})

    def test_fixture_tar_numeric_owners_custody_and_short_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary)/'binary'
            binary.write_bytes(b'fixture-not-an-executable')
            archive, configs = CHECK.fixture_archive(dict(debug=binary, release=binary))
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            names = {m.name: m for m in tar}
            self.assertEqual(names['ingress'].mode, 0o711)
            for profile, config in configs.items():
                self.assertEqual(names[f'ingress/{profile}/p'].mode, 0o750)
                self.assertEqual(names[f'ingress/{profile}/operator'].mode, 0o700)
                self.assertEqual(names[f'ingress/{profile}/state'].mode, 0o700)
                state = Path(config['state_database']).parent
                for key in ('producer_socket', 'operator_socket'):
                    parent = Path(config['protected_ingress'][key]).parent
                    self.assertEqual(parent.parent, state.parent)
                    self.assertNotEqual(parent, state)
                    self.assertFalse(parent.is_relative_to(state))
                    self.assertFalse(state.is_relative_to(parent))
                for m in names.values():
                    self.assertEqual((m.uid, m.gid), (1000, 1001))
                    self.assertTrue(m.isfile() or m.isdir())
                for key in ('producer_socket', 'operator_socket'):
                    self.assertLessEqual(len(config['protected_ingress'][key].encode()), 107)
                self.assertEqual(config['protected_ingress']['proxy_uid'], 1001)
                self.assertTrue(config['check_expected_sizes'])
                saved = json.load(tar.extractfile(f'ingress/{profile}/config.json'))
                self.assertEqual(saved, config)

    @unittest.skipUnless(shutil.which('perl'), 'portable Perl unavailable')
    def test_perl_clients_parse(self):
        for client in (CHECK.CLIENT, CHECK.PROXY_CAPACITY, CHECK.OPERATOR_CAPACITY, CHECK.LOST_CLIENT):
            result = subprocess.run(['perl', '-c', '-e', client], capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which('perl') and hasattr(socket, 'AF_UNIX'), 'Unix/Perl unavailable')
    def test_actual_perl_unix_client_handles_early_reply(self):
        with tempfile.TemporaryDirectory(prefix='ingress-client-') as temporary:
            endpoint = temporary+'/s'
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(endpoint)
            server.listen(1)
            errors = []
            def serve():
                try:
                    connection, _ = server.accept()
                    with connection:
                        connection.sendall(reply(429, {'error': 'rate_limited'}))
                        connection.shutdown(socket.SHUT_WR)
                        while connection.recv(8192):
                            pass
                except Exception as error:
                    errors.append(error)
            worker = threading.Thread(target=serve, daemon=True)
            worker.start()
            raw = CHECK.wire(body={'large': 'x'*65536})
            result = subprocess.run(['perl', '-e', CHECK.CLIENT, endpoint, *CHECK.client_arguments(raw)], capture_output=True, timeout=5)
            worker.join(timeout=2)
            server.close()
            self.assertFalse(worker.is_alive())
            self.assertFalse(errors)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(CHECK.parse_reply(bytes.fromhex(result.stdout.decode('ascii')))['code'], 429)

    def test_gate_rejects_wrong_mode_source_and_artifact_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'rust').mkdir()
            (root/'scripts').mkdir()
            folder = root/'gate'
            folder.mkdir()
            (root/'rust/lib.rs').write_bytes(b'fixture source')
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            def commit_source():
                subprocess.run(['git', 'add', '--', 'rust'], cwd=root, check=True)
                subprocess.run(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                                'commit', '-q', '-m', 'Test: Committed fixture source'], cwd=root, check=True)
            commit_source()
            platform = {'runtime': 'example.invalid/runtime@sha256:'+'a'*64}
            (root/'scripts/rust-platform.json').write_text(json.dumps(platform))
            # A tiny stand-in tests gate binding only, never claims a real ELF audit.
            (root/'scripts/check-rust-sles.py').write_text("def audit(text):\n    assert text == 'elf evidence'\n    return {'verified': True}\n")
            archive = io.BytesIO()
            with tarfile.open(fileobj=archive, mode='w:gz') as tar:
                item = tarfile.TarInfo('lib.rs')
                item.size = len(b'fixture source')
                tar.addfile(item, io.BytesIO(b'fixture source'))
            (folder/'source.tar.gz').write_bytes(archive.getvalue())
            gate = dict(status='PASSED', build_mode='production', config=platform, run_id='fixture',
                        source_sha256=CHECK.sha(archive.getvalue()), profiles={})
            for profile in ('debug', 'release'):
                name = profile+'-0-file-mover'
                (folder/name).write_bytes(profile.encode())
                (folder/(name+'.elf')).write_text('elf evidence')
                gate['profiles'][profile] = dict(tests_passed=1, artifacts=[dict(name=name, test=False,
                    sha256=CHECK.sha(profile.encode()), elf={'verified': True})])
            def save(value):
                (folder/'report.json').write_text(json.dumps(value))
            save(gate)
            _, artifacts, _ = CHECK.load_gate(folder, root)
            self.assertEqual(set(artifacts), {'debug', 'release'})
            bad = copy.deepcopy(gate)
            bad['build_mode'] = 'nfs-qualification'
            save(bad)
            with self.assertRaises(AssertionError): CHECK.load_gate(folder, root)
            save(gate)
            # Worktree bytes, including Windows CRLF, cannot relabel committed evidence.
            (root/'rust/lib.rs').write_bytes(b'fixture source\r\n')
            CHECK.load_gate(folder, root)
            (root/'rust/lib.rs').write_bytes(b'changed')
            commit_source()
            with self.assertRaises(AssertionError): CHECK.load_gate(folder, root)
            (root/'rust/lib.rs').write_bytes(b'fixture source')
            commit_source()
            (folder/'debug-0-file-mover').write_bytes(b'tampered')
            with self.assertRaises(AssertionError): CHECK.load_gate(folder, root)


if __name__ == '__main__':
    unittest.main()
