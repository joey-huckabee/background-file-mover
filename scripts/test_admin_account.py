"""Portable stdlib tests for the account PTY checker; no Podman or SLES."""
import importlib.util
import io
import json
import os
from pathlib import Path
import pty
import selectors
import subprocess
import sys
import tarfile
import termios
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location('admin_account_checker', Path(__file__).with_name('check-admin-account.py'))
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


class Capture(unittest.TestCase):
    def test_split_secret_rejected_without_echo_in_exception(self):
        capture = checker.PrivateCapture((b'disposable-secret',))
        capture.append(b'prompt: disposable-')
        with self.assertRaises(checker.CheckError) as failure:
            capture.append(b'secret')
        self.assertNotIn('disposable-secret', str(failure.exception))
        capture.clear()
        self.assertEqual(capture.data, b'')
        self.assertEqual(capture.secret_values, [])

    def test_bounds_sensitive_material_and_incremental_markers(self):
        capture = checker.PrivateCapture()
        capture.append(b'FM_PID 123 456\r\npassword: ')
        match = capture.match(rb'FM_PID ([0-9]+) ([0-9]+)\r?\n')
        self.assertEqual(match.groups(), (b'123', b'456'))
        self.assertIsNone(capture.match(rb'FM_PID'))
        self.assertIsNotNone(capture.match(rb'password: '))
        for value in (b'$argon2id$v=19$private', b'-----BEGIN PRIVATE KEY-----', b'"verifier": "private"'):
            with self.subTest(value=value), self.assertRaises(checker.CheckError):
                checker.PrivateCapture().append(value)
        exact = checker.PrivateCapture()
        exact.append(b'x'*checker.LIMIT)
        with self.assertRaises(checker.CheckError):
            exact.append(b'x')

    def test_inner_echo_flags_and_strict_public_status(self):
        self.assertTrue(checker.echo_enabled(b'1:2:3:b:0:0'))
        self.assertFalse(checker.echo_enabled(b'1:2:3:3:0:0'))
        for value in (b'', b'x:2:3:4', b'8', b'1:2:3:4\nprivate'):
            with self.assertRaises(checker.CheckError):
                checker.echo_enabled(value)
        with self.assertRaises(ValueError):
            checker.public_status(b'{"provisioned":true,"provisioned":false}', 1)
        status = dict(provisioned=True, version=1, username=checker.USERNAME, revision='2')
        self.assertEqual(checker.public_status(json.dumps(status).encode(), 2), status)
        for modification in ({'verifier':'private'}, {'revision':True}, {'revision':1}, {'revision':2}, {'revision':'02'}, {'version':True}):
            bad = dict(status, **modification)
            with self.assertRaises(checker.CheckError):
                checker.public_status(json.dumps(bad).encode(), 2)


class PortableProcess(unittest.TestCase):
    def test_bounded_private_command_and_error_redaction(self):
        runner = checker.Runner()
        result = runner.command([sys.executable, '-c', 'import sys; print("public"); sys.stderr.write("diagnostic")'])
        self.assertEqual(result.stdout, b'public\n')
        self.assertEqual(result.stderr, b'diagnostic')
        for script in ('import sys; print("private-password"); sys.exit(1)',
                       'import os; os.write(1,b"x"*100000)',
                       'import time; time.sleep(2)'):
            with self.subTest(script=script), self.assertRaises(checker.CheckError) as failure:
                runner.command([sys.executable, '-c', script], timeout=0.1)
            self.assertNotIn('private-password', str(failure.exception))

    def test_nonterminal_commands_have_private_visible_session(self):
        runner = checker.Runner()
        runner.container = 'owned-id'
        runner.command = Mock()
        runner.execute('/tmp/file-mover', '--initialize-source', '/tmp/config')
        self.assertEqual(runner.command.call_args.args[0],
            ['podman', 'exec', '--user', checker.USER, 'owned-id', '/usr/bin/setsid', '--wait',
             '/tmp/file-mover', '--initialize-source', '/tmp/config'])

    def test_actual_host_pty_selectors_match_without_container(self):
        master, slave = pty.openpty()
        process = subprocess.Popen([sys.executable, '-c', 'import os; os.write(1,b"FM_TEST 123\\n")'],
                                   stdin=slave, stdout=slave, stderr=slave)
        os.close(slave)
        terminal = checker.Terminal.__new__(checker.Terminal)
        terminal.master, terminal.process = master, process
        terminal.selector = selectors.DefaultSelector()
        terminal.capture = checker.PrivateCapture()
        os.set_blocking(master, False)
        terminal.selector.register(master, selectors.EVENT_READ)
        try:
            self.assertEqual(terminal.expect(rb'FM_TEST ([0-9]+)\r?\n').group(1), b'123')
            self.assertEqual(process.wait(timeout=2), 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=2)
            terminal.close()

    def test_exec_uses_pty_and_never_password_arguments(self):
        runner = checker.Runner()
        runner.container = 'owned-container'
        process = Mock()
        with patch.object(checker.subprocess, 'Popen', return_value=process) as spawn:
            terminal = checker.Terminal(runner, '/tmp/app', '/tmp/config', '/tmp/account',
                                        '--admin-account-init', (b'private-password',))
        try:
            argv = spawn.call_args.args[0]
            self.assertEqual(argv[:6], ['podman', 'exec', '-it', '--user', checker.USER, 'owned-container'])
            self.assertIn('--admin-account-init', argv)
            self.assertNotIn('private-password', ' '.join(argv))
            self.assertEqual(runner.processes, [process])
            self.assertEqual(spawn.call_args.kwargs['stdin'], spawn.call_args.kwargs['stdout'])
        finally:
            terminal.close()

    def test_wrapper_and_precise_signal_identity(self):
        self.assertIn('tcsetpgrp', checker.WRAPPER)
        self.assertIn('waitpid', checker.WRAPPER)
        for marker in ('FM_BEFORE', 'FM_TTY', 'FM_PID', 'FM_AFTER', 'FM_EXIT'):
            self.assertIn(marker, checker.WRAPPER)
        self.assertIn('$fields[19] eq $start', checker.TERM)
        self.assertIn('readlink("/proc/$pid/exe") eq $binary', checker.TERM)
        self.assertIn("kill('TERM',$pid)", checker.TERM)


class ProfileFlow(unittest.TestCase):
    def test_five_cases_use_only_tty_secrets_and_public_reports(self):
        runner = Mock()
        statuses = iter([1, 1, 1, 1, 2])
        def execute(*argv):
            if argv[0] == 'sha256sum':
                return subprocess.CompletedProcess(argv, 0, b'a'*64+b'  account\n', b'')
            if '--admin-account-status' in argv:
                payload = dict(provisioned=True, version=1, username=checker.USERNAME, revision=str(next(statuses)))
                return subprocess.CompletedProcess(argv, 0, json.dumps(payload).encode(), b'')
            return subprocess.CompletedProcess(argv, 0, b'', b'')
        runner.execute.side_effect = execute
        terminals = []
        def terminal_factory(*args):
            terminal = Mock(pid='123', starttime='456')
            terminal.finish.return_value = dict(exit_code=0, echo_disabled=True, terminal_restored=True, secret_free=True)
            terminals.append((terminal, args[-1]))
            return terminal
        record = dict(profile='debug', cases=[], passed=False)
        with patch.object(checker, 'Terminal', side_effect=terminal_factory):
            checker.run_profile(runner, 'debug', {'sha256':'public'}, record)
        self.assertTrue(record['passed'])
        self.assertEqual([case['case'] for case in record['cases']], ['init','mismatch','ctrl-c','sigterm','change'])
        self.assertEqual([case['status']['revision'] for case in record['cases']], ['1','1','1','1','2'])
        self.assertEqual(terminals[2][0].send.call_args.args, (b'\x03',))
        calls = runner.execute.call_args_list
        term = [call.args for call in calls if checker.TERM in call.args]
        self.assertEqual(len(term), 1)
        self.assertEqual(term[0][-3:], ('123','456','/tmp/ingress/debug/file-mover'))
        public = json.dumps(record).encode()
        all_argv = repr(calls).encode()
        for terminal, values in terminals:
            terminal.close.assert_called_once()
            for value in values:
                self.assertNotIn(value, public)
                self.assertNotIn(value, all_argv)


class FixtureAndReporting(unittest.TestCase):
    def test_failed_create_never_claims_or_removes_an_existing_name(self):
        runner = checker.Runner()
        runner.command = Mock(side_effect=checker.CheckError('private fixture command failed'))
        with self.assertRaises(checker.CheckError):
            checker.create_container(runner, 'pinned-image')
        self.assertFalse(runner.container)
        runner.close()
        self.assertEqual(runner.command.call_count, 1)
        created = subprocess.CompletedProcess([], 0, b'a'*64+b'\n', b'')
        runner.command = Mock(return_value=created)
        self.assertEqual(checker.create_container(runner, 'pinned-image'), 'a'*64)
        runner.close()
        self.assertEqual(runner.command.call_args.args[0], ['podman', 'rm', '-f', 'a'*64])

    def test_tar_keeps_numeric_custody_and_exact_trailer(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w') as out:
            entry = tarfile.TarInfo('ingress/debug/public')
            entry.mode, entry.uid, entry.gid, entry.size = 0o600, 1000, 1001, 6
            out.addfile(entry, io.BytesIO(b'public'))
        helpers = Mock()
        helpers.fixture_archive.return_value = (buffer.getvalue(), {'debug':{'public':True}})
        archive, configs = checker.fixture_archive(helpers, {})
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:') as tar:
            self.assertEqual(tar.extractfile('ingress/debug/public').read(), b'public')
            for profile in ('debug', 'release'):
                member = tar.getmember('ingress/'+profile+'/account')
                self.assertTrue(member.isdir())
                self.assertEqual((member.uid, member.gid, member.mode), (1000, 1001, 0o700))
            end = tar.offset
        self.assertEqual(archive[end:], bytes(1024))
        self.assertEqual(configs, {'debug':{'public':True}})

    def test_existing_report_refused_before_gate_or_container(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory)/'report.json'
            report.write_text('original')
            with patch.object(checker, 'ingress_helpers') as helpers, self.assertRaises(checker.CheckError):
                checker.main(['--production-gate', directory, '--report', str(report)])
            helpers.assert_not_called()
            self.assertEqual(report.read_text(), 'original')


if __name__ == '__main__':
    unittest.main()
