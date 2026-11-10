"""Client-driver safety/provenance cases; real TLS lives in check-tls-clients."""
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('tls_clients_driver', Path(__file__).with_name('check-tls-clients.py'))
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


class Safety(unittest.TestCase):
    def test_certificate_alerts_only_not_timeout_tcp_or_empty_success(self):
        row = dict(exit_code=35, code=0, stderr='* TLSv1.2 (IN), TLS alert, unknown CA (560):')
        self.assertTrue(driver.tls_rejection(row))
        self.assertTrue(driver.tls_rejection(dict(row, exit_code=98)))
        self.assertTrue(driver.tls_rejection(dict(row, exit_code=60,
            stderr='* TLSv1.2 (IN), TLS alert, certificate expired (557):\ncurl: (60) SSL certificate verification failed')))
        self.assertFalse(driver.tls_rejection(dict(row, exit_code=60,
            stderr='* TLSv1.2 (OUT), TLS alert, unknown CA (560):\ncurl: (60) SSL certificate verification failed')))
        self.assertFalse(driver.tls_rejection(dict(row, exit_code=60, stderr='SSL certificate verification failed')))
        self.assertFalse(driver.tls_rejection(dict(row,
            stderr=row['stderr']+'\n* TLSv1.2 (OUT), TLS alert, unknown CA (560):')))
        self.assertTrue(driver.tls_rejection(dict(row,
            stderr=row['stderr']+'\n* TLSv1.2 (OUT), TLS alert, close notify (256):')))
        missing = '* TLSv1.2 (IN), TLS alert, unknown (628):\nOpenSSL: error:0A00045C:SSL routines::tlsv13 alert certificate required'
        self.assertTrue(driver.tls_rejection(dict(row, exit_code=98, stderr=missing)))
        self.assertFalse(driver.tls_rejection(dict(row, exit_code=98, stderr=missing.replace('(IN)', '(OUT)'))))
        self.assertFalse(driver.tls_rejection(dict(row, exit_code=60, stderr='* TLSv1.2 (IN), TLS alert, unknown (628):')))
        for exit_code in (0, 6, 7, 28, 52, 58, -9):
            self.assertFalse(driver.tls_rejection(dict(row, exit_code=exit_code)))
        self.assertFalse(driver.tls_rejection(dict(row, code=403)))
        self.assertFalse(driver.tls_rejection(dict(row, stderr='connection reset by peer')))
        openssl = dict(row, exit_code=1, stderr='verify return:1\nSSL routines: tlsv13 alert certificate required')
        self.assertTrue(driver.openssl_rejection(openssl))
        self.assertFalse(driver.openssl_rejection(dict(openssl, stderr='unexpected EOF')))
        self.assertFalse(driver.openssl_rejection(dict(openssl, exit_code=0)))
        self.assertFalse(driver.openssl_rejection(dict(openssl, stderr='alert certificate required')))

    def test_session_or_key_diagnostics_never_become_report_text(self):
        self.assertIn('verify return:1', driver.diagnostics(b'verify return:1'))
        for marker in (b'PRIVATE KEY', b'Master-Key:', b'CLIENT_RANDOM', b'CLIENT_TRAFFIC_SECRET',
                       b'Resumption PSK:', b'SSL-Session:', b'Session-ID:'):
            with self.assertRaisesRegex(AssertionError, 'unexpected sensitive'):
                driver.diagnostics(b'private sentinel '+marker)
        with self.assertRaises(AssertionError):
            driver.diagnostics(b'x'*16385)

    def test_tar_preserves_zero_payload_private_modes_and_exact_end_blocks(self):
        payload = b'content'+bytes(20000)
        data = driver.archive([('private', 0o700, None), ('private/secret.key.der', 0o600, payload)])
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            members = tar.getmembers()
            self.assertEqual(tar.extractfile(members[1]).read(), payload)
            self.assertEqual((members[1].uid, members[1].gid, members[1].mode), (1000, 1001, 0o600))
            end = members[1].offset_data+((len(payload)+511)//512)*512
        self.assertEqual(data[end:], bytes(1024))
        for name in ('/absolute', '../escape', 'a/../../escape'):
            with self.assertRaises(AssertionError):
                driver.archive([(name, 0o600, b'')])

    def test_failed_network_creation_never_removes_an_existing_name(self):
        lab = driver.Lab({})
        with patch.object(lab, 'command', side_effect=RuntimeError('already exists')):
            with self.assertRaises(RuntimeError):
                lab.create('runtime', 'client')
        self.assertIsNone(lab.network)
        self.assertIsNone(lab.container)
        self.assertIsNone(lab.client)

    def test_existing_report_refuses_before_any_container_side_effect(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder)/'existing.json'
            report.write_bytes(b'original evidence')
            args = ['check-tls-clients.py', '--production-gate', folder, '--report', str(report)]
            with patch.object(sys, 'argv', args), patch.object(driver.Lab, 'create') as create:
                with self.assertRaises(FileExistsError):
                    driver.main()
                create.assert_not_called()
            self.assertEqual(report.read_bytes(), b'original evidence')

    def test_client_removal_timeout_still_cleans_server_process_and_network(self):
        report = {}
        lab = driver.Lab(report)
        lab.client, lab.container, lab.network = 'owned-client', 'owned-server', 'owned-network'
        process = Mock()
        process.poll.return_value = None
        lab.processes = [process]
        commands = []

        def command(args, **kwargs):
            commands.append(args)
            if args == ['podman', 'rm', '-f', 'owned-client']:
                raise subprocess.TimeoutExpired(args, 20)
            return subprocess.CompletedProcess(args, 0, b'removed', b'')

        with patch.object(lab, 'command', side_effect=command):
            with self.assertRaisesRegex(AssertionError, 'client cleanup: TimeoutExpired'):
                lab.close()
        self.assertIn(['podman', 'rm', '-f', 'owned-server'], commands)
        self.assertIn(['podman', 'network', 'rm', 'owned-network'], commands)
        process.terminate.assert_called_once()
        process.communicate.assert_called_once_with(timeout=5)
        self.assertEqual(report['cleanup']['exit_code'], 0)
        self.assertEqual(report['network_cleanup_exit_code'], 0)

    def test_archive_separates_server_private_keys_from_clients(self):
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder)/'file-mover'
            binary.write_bytes(b'unit executable placeholder')
            der = {name: b'unit DER placeholder '+name.encode() for name in driver.tls_proof_fixture.FILES}
            server, client, configs = driver.fixtures({'debug': binary, 'release': binary}, der)
            with tarfile.open(fileobj=io.BytesIO(server)) as tar:
                names = tar.getnames()
                self.assertFalse(any('client.key' in n for n in names))
                self.assertTrue(any(n.endswith('server.key.der') for n in names))
            with tarfile.open(fileobj=io.BytesIO(client)) as tar:
                names = tar.getnames()
                self.assertFalse(any('server.key' in n for n in names))
                self.assertTrue(any(n.endswith('client.key.der') for n in names))
            for config in configs.values():
                self.assertEqual(config['native_ingress']['authority'], 'localhost:19879')
                self.assertNotEqual(Path(config['state_database']).parent,
                                    Path(config['native_ingress']['operator_socket']).parent)


@unittest.skipUnless(os.name == 'posix', 'driver requires Linux pipe/container execution')
class BoundedProcesses(unittest.TestCase):
    def test_closed_private_diagnostics_preserve_original_status_and_bytes(self):
        lab = driver.Lab({})

        def local(*args, data=None, discard=False, ok=True, timeout=15):
            result = driver.bounded_client(list(args), data=data, discard=discard, timeout=timeout)
            if ok:
                self.assertEqual(result.returncode, 0)
            return result

        with tempfile.TemporaryDirectory() as folder, patch.object(lab, 'client_exec', side_effect=local):
            path = str(Path(folder)/'private.stderr')
            code = 'import sys;sys.stdout.write("response");sys.stderr.write("verify return:1\\n");sys.exit(7)'
            result = lab.client_tool([sys.executable, '-c', code], path)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (7, b'response', b'verify return:1\n'))
            self.assertEqual(Path(path).stat().st_mode & 0o777, 0o600)

    def test_stream_both_pipes_while_writing_and_discard_receipt_without_capture(self):
        code = 'import sys; data=sys.stdin.buffer.read(); sys.stdout.buffer.write(data); sys.stderr.write("verified")'
        result = driver.bounded_client([sys.executable, '-c', code], data=bytes(65536))
        self.assertEqual((result.returncode, len(result.stdout), result.stderr), (0, 65536, b'verified'))
        result = driver.bounded_client([sys.executable, '-c', code], data=b'HTTP receipt', discard=True)
        self.assertEqual(result.stdout, b'')
        self.assertEqual(result.stderr, b'verified')

    def test_excess_output_and_stalled_child_fail_instead_of_qualifying(self):
        with self.assertRaisesRegex(AssertionError, 'output exceeds bound'):
            driver.bounded_client([sys.executable, '-c', 'import sys;sys.stdout.buffer.write(bytes(131073))'])
        with self.assertRaisesRegex(AssertionError, 'output exceeds bound'):
            driver.bounded_client([sys.executable, '-c', 'import sys;sys.stderr.buffer.write(bytes(16385))'])
        with self.assertRaises((AssertionError, subprocess.TimeoutExpired)):
            driver.bounded_client([sys.executable, '-c', 'import select;select.select([],[],[],2)'], timeout=0.1)


if __name__ == '__main__':
    unittest.main()
