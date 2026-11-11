#!/usr/bin/env python3
"""Disposable offline account CLI/PTTY qualification; coordinator executes SLES.

python3 scripts/check-admin-account.py --production-gate PATH --report NEWPATH
No builds/downloads/installations, daemon, remote auth or operational state.
All captured CLI/terminal bytes stay private in memory, including on failure.
"""
import argparse
import errno
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import pty
import re
import secrets
import selectors
import subprocess
import tarfile
import tempfile
import termios
import time

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 65536
USER = '1000:1001'
USERNAME = 'fixture-admin'


class CheckError(ValueError):
    """Only fixed public labels may enter reports."""


def require(condition, label):
    if not condition:
        raise CheckError(label)


def ingress_helpers():
    spec = importlib.util.spec_from_file_location('admin_ingress_helpers', ROOT/'scripts/check-producer-ingress.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# One persistent inner controlling terminal. The wrapper owns a foreground child
# group so Ctrl-C reaches the actual app, not just the host podman client. The
# pipe prevents exec before the parent establishes foreground ownership/markers.
# This fixed program has no secret literals or interpolated shell arguments.
WRAPPER = r'''
use strict; use warnings; use POSIX qw(setpgid tcsetpgrp getpgrp);
$|=1; $SIG{TTOU}='IGNORE'; alarm 45;
open(my $tty,'+<','/dev/tty') or die 'controlling tty unavailable';
sub flags { my $s=`stty -g < /dev/tty`; $?==0 or die 'stty unavailable'; chomp($s); return $s; }
my $name=`tty`; $?==0 or die 'tty unavailable'; chomp($name);
print "FM_BEFORE ",flags(),"\nFM_TTY ",$name,"\n";
pipe(my $read,my $write) or die 'pipe';
my $pid=fork(); defined($pid) or die 'fork';
if(!$pid) {
  close($write); sysread($read,my $go,1)==1 or die 'start'; close($read);
  exec {$ARGV[0]} @ARGV; die 'exec failed';
}
close($read);
setpgid($pid,$pid)==0 or die 'process group';
tcsetpgrp(fileno($tty),$pid)==0 or die 'foreground tty';
open(my $stat,'<',"/proc/$pid/stat") or die 'child identity';
my $row=<$stat>; close($stat); $row =~ /^\d+ \(.*\) (.*)$/ or die 'stat';
my @fields=split(/ /,$1); my $start=$fields[19];
print "FM_PID $pid $start\n";
syswrite($write,'x',1)==1 or die 'release'; close($write);
my $wait; do { $wait=waitpid($pid,0); } while($wait<0 && $!{EINTR});
$wait==$pid or die 'wait'; my $status=$?;
tcsetpgrp(fileno($tty),getpgrp())==0 or die 'restore foreground';
print "\nFM_AFTER ",flags(),"\nFM_EXIT ",($status & 127 ? 128+($status & 127) : $status >> 8),"\n";
'''

# Exact child PID + Linux starttime + executable checks; never a process-name kill.
TERM = r'''
use strict; use warnings;
my($pid,$start,$binary)=@ARGV;
$pid =~ /^[1-9][0-9]*$/ && $start =~ /^[0-9]+$/ or die 'identity';
open(my $h,'<',"/proc/$pid/stat") or die 'identity missing'; my $row=<$h>; close($h);
$row =~ /^\d+ \(.*\) (.*)$/ or die 'identity'; my @fields=split(/ /,$1);
$fields[19] eq $start && readlink("/proc/$pid/exe") eq $binary or die 'identity changed';
kill('TERM',$pid)==1 or die 'signal';
'''


def echo_enabled(flags):
    require(bool(re.fullmatch(rb'[0-9a-fA-F]+(?::[0-9a-fA-F]+){3,}', flags)), 'invalid terminal flag observation')
    return bool(int(flags.split(b':')[3], 16) & termios.ECHO)


def public_status(raw, revision):
    def unique(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate public account status field')
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError):
        raise ValueError('invalid public account status') from None
    require(isinstance(value, dict) and set(value) == {'provisioned', 'version', 'username', 'revision'},
            'unexpected account status fields')
    require(value['provisioned'] is True and type(value['version']) is int and value['version'] == 1
            and value['username'] == USERNAME and type(value['revision']) is str and value['revision'] == str(revision),
            'unexpected public account status')
    return value


class PrivateCapture:
    """Bounded in-memory transcript. Never stringify this object or its bytes."""
    def __init__(self, secret_values=()):
        self.data = bytearray()
        self.offset = 0
        self.secret_values = list(secret_values)

    def append(self, data):
        require(len(self.data) + len(data) <= LIMIT, 'private terminal capture exceeded bound')
        self.data.extend(data)
        raw = bytes(self.data)
        require(not any(secret in raw for secret in self.secret_values), 'secret input was echoed')
        require(not re.search(rb'\$argon2(?:id|i|d)\$|PRIVATE KEY|SSL-Session:|Master-Key:|"verifier"', raw),
                'unexpected sensitive terminal output')

    def match(self, expression):
        match = re.search(expression, self.data[self.offset:], re.I)
        if match:
            self.offset += match.end()
        return match

    def clear(self):
        self.data[:] = b'\0' * len(self.data)
        self.data.clear()
        self.secret_values.clear()


class Terminal:
    def __init__(self, runner, binary, config, account, action, secret_values):
        self.capture = PrivateCapture(secret_values)
        self.runner = runner
        self.master, slave = pty.openpty()
        self.selector = selectors.DefaultSelector()
        self.process = None
        try:
            flags = termios.tcgetattr(slave)
            flags[3] &= ~termios.ECHO  # Never echo on the host PTY either.
            termios.tcsetattr(slave, termios.TCSANOW, flags)
            argv = ['podman', 'exec', '-it', '--user', USER, runner.container,
                    '/usr/bin/perl', '-e', WRAPPER, binary, action, config, '--account-dir', account]
            self.process = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave)
            runner.processes.append(self.process)
            os.set_blocking(self.master, False)
            self.selector.register(self.master, selectors.EVENT_READ)
        except BaseException:
            self.close()
            raise
        finally:
            os.close(slave)

    def expect(self, expression, seconds=12):
        deadline = time.monotonic() + seconds
        while True:
            match = self.capture.match(expression)
            if match:
                return match
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'terminal expectation timed out')
            if not self.selector.select(min(remaining, 0.25)):
                require(self.process.poll() is None, 'terminal command exited before expected marker')
                continue
            try:
                data = os.read(self.master, 4096)
            except OSError as error:
                if error.errno == errno.EIO:
                    raise ValueError('terminal closed before expected marker') from None
                raise ValueError('terminal read failed') from None
            require(bool(data), 'terminal closed before expected marker')
            self.capture.append(data)

    def send(self, data):
        view = memoryview(data)
        deadline = time.monotonic() + 3
        while view:
            require(time.monotonic() < deadline, 'terminal write timed out')
            try:
                count = os.write(self.master, view)
            except BlockingIOError:
                raise ValueError('terminal write blocked') from None
            require(count > 0, 'terminal write failed')
            view = view[count:]

    def start(self):
        self.before = self.expect(rb'FM_BEFORE ([0-9a-f:]+)\r?\n').group(1)
        require(echo_enabled(self.before), 'inner terminal did not start with echo enabled')
        self.tty = self.expect(rb'FM_TTY (/dev/pts/[0-9]+)\r?\n').group(1).decode()
        identity = self.expect(rb'FM_PID ([1-9][0-9]*) ([0-9]+)\r?\n')
        self.pid, self.starttime = (value.decode() for value in identity.groups())

    def password_prompt(self):
        self.expect(rb'(?:password|passphrase)[^\r\n:]{0,80}: ?')
        flags = self.runner.execute('stty', '-g', '-F', self.tty).stdout.strip()
        require(not echo_enabled(flags), 'inner password prompt has echo enabled')

    def finish(self, success):
        after = self.expect(rb'FM_AFTER ([0-9a-f:]+)\r?\n', seconds=20).group(1)
        code = int(self.expect(rb'FM_EXIT ([0-9]+)\r?\n').group(1))
        require(after == self.before and echo_enabled(after), 'inner terminal flags were not restored')
        require((code == 0) == success, 'unexpected account command exit code')
        try:
            require(self.process.wait(timeout=5) == 0, 'terminal wrapper failed')
        except subprocess.TimeoutExpired:
            raise ValueError('terminal wrapper did not exit') from None
        # Drain any already-buffered output as well; never publish the transcript.
        while True:
            try:
                data = os.read(self.master, 4096)
            except BlockingIOError:
                break
            except OSError as error:
                require(error.errno == errno.EIO, 'terminal final read failed')
                break
            if not data:
                break
            self.capture.append(data)
        return dict(exit_code=code, echo_disabled=True, terminal_restored=True, secret_free=True)

    def close(self):
        self.selector.close()
        if self.master is not None:
            os.close(self.master)
            self.master = None
        self.capture.clear()


class Runner:
    def __init__(self):
        self.container = None
        self.processes = []

    def command(self, argv, timeout=20, stdin=None):
        # Bound capture while reading, not after subprocess.run has accumulated it.
        chunks = [bytearray(), bytearray()]
        process = None
        try:
            process = subprocess.Popen(argv, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            with selectors.DefaultSelector() as selector:
                for index, pipe in enumerate((process.stdout, process.stderr)):
                    os.set_blocking(pipe.fileno(), False)
                    selector.register(pipe, selectors.EVENT_READ, index)
                deadline = time.monotonic() + timeout
                while selector.get_map():
                    require(time.monotonic() < deadline, 'private fixture command timed out')
                    for key, _ in selector.select(min(0.25, max(0, deadline-time.monotonic()))):
                        data = os.read(key.fileobj.fileno(), 4096)
                        if not data:
                            selector.unregister(key.fileobj)
                            continue
                        require(sum(map(len, chunks)) + len(data) <= LIMIT, 'private fixture output exceeded bound')
                        chunks[key.data].extend(data)
                try:
                    code = process.wait(timeout=max(0.01, deadline-time.monotonic()))
                except subprocess.TimeoutExpired:
                    raise CheckError('private fixture command timed out') from None
            require(code == 0, 'private fixture command failed')
            return subprocess.CompletedProcess(argv, code, bytes(chunks[0]), bytes(chunks[1]))
        except OSError:
            raise CheckError('private fixture command unavailable') from None
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()  # Only this exact host CLI process.
                    process.wait(timeout=5)
                process.stdout.close()
                process.stderr.close()
            for chunk in chunks:
                chunk[:] = b'\0' * len(chunk)

    def execute(self, *argv):
        return self.command(['podman', 'exec', '--user', USER, self.container, *argv])

    def close(self):
        clean = True
        if self.container:
            try:
                self.command(['podman', 'rm', '-f', self.container])
            except Exception:
                clean = False
        for process in self.processes:
            if process.poll() is None:
                process.terminate()  # Exact owned host CLI, never a process-name kill.
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        require(clean, 'owned container cleanup failed')


def fixture_archive(helpers, artifacts):
    old, configs = helpers.fixture_archive(artifacts)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(old), mode='r:') as source, tarfile.open(fileobj=buffer, mode='w') as out:
        for member in source.getmembers():
            require(member.isfile() or member.isdir(), 'unsafe fixture tar member')
            out.addfile(member, source.extractfile(member) if member.isfile() else None)
        for profile in ('debug', 'release'):
            entry = tarfile.TarInfo('ingress/'+profile+'/account')
            entry.type, entry.mode, entry.uid, entry.gid = tarfile.DIRTYPE, 0o700, 1000, 1001
            out.addfile(entry)
        end = out.offset
    return buffer.getvalue()[:end + 1024], configs


def fingerprint(runner, account):
    # Only an ephemeral equality token: never retained in reports or errors.
    raw = runner.execute('sha256sum', account+'/admin-account.json').stdout
    digest = raw.split(maxsplit=1)[0]
    require(bool(re.fullmatch(rb'[0-9a-f]{64}', digest)), 'invalid private account equality observation')
    return digest


def run_profile(runner, profile, artifact, record):
    base = '/tmp/ingress/'+profile
    binary, config, account = base+'/file-mover', base+'/config.json', base+'/account'
    runner.execute(binary, '--initialize-source', config)
    rows = record['cases']
    for action in ('init', 'mismatch', 'ctrl-c', 'sigterm', 'change'):
        row = dict(case=action, passed=False)
        rows.append(row)
        password = secrets.token_urlsafe(24).encode()
        confirm = secrets.token_urlsafe(24).encode() if action == 'mismatch' else password
        before = fingerprint(runner, account) if action != 'init' else None
        command = '--admin-account-init' if action == 'init' else '--admin-password-change'
        terminal = Terminal(runner, binary, config, account, command, (password, confirm))
        started = time.monotonic()
        try:
            terminal.start()
            if action == 'init':
                terminal.expect(rb'user(?:name)?[^\r\n:]{0,80}: ?')
                terminal.send(USERNAME.encode()+b'\n')
            terminal.password_prompt()
            if action in ('ctrl-c', 'sigterm'):
                terminal.send(password)  # Partial secret input, no line terminator.
                if action == 'ctrl-c':
                    terminal.send(b'\x03')
                else:
                    runner.execute('/usr/bin/perl', '-e', TERM, terminal.pid, terminal.starttime, binary)
            else:
                terminal.send(password+b'\n')
                terminal.password_prompt()
                terminal.send(confirm+b'\n')
            row.update(terminal.finish(action in ('init', 'change')))
            row.update(case=action, seconds=round(time.monotonic()-started, 3))
        finally:
            terminal.close()
        if action in ('mismatch', 'ctrl-c', 'sigterm'):
            require(fingerprint(runner, account) == before, 'interrupted account command changed credentials')
            row['credentials_unchanged'] = True
        revision = 2 if action == 'change' else 1
        row['status'] = public_status(runner.execute(binary, '--admin-account-status', config,
                                                    '--account-dir', account).stdout, revision)
        row['passed'] = True
    record['passed'] = True


def create_container(runner, image):
    name = 'admin-account-pty-'+secrets.token_hex(10)
    created = runner.command(['podman', 'create', '--name', name, '--pull=never', '--network', 'none', '--user', USER,
                              '--cap-drop', 'all', '--security-opt', 'no-new-privileges',
                              '--entrypoint', '/bin/sh', image, '-c', 'exec sleep infinity'])
    identity = created.stdout.decode().strip()
    require(bool(re.fullmatch(r'[0-9a-f]{64}', identity)), 'invalid owned container identity')
    # Only a successful creation with a validated ID establishes cleanup ownership.
    runner.container = identity
    return identity


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production-gate', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args(argv)
    require(not args.report.exists(), 'report already exists')
    report = dict(status='FAILED', profiles=[], limits=[
        'Disposable offline local PTY CLI only; no remote auth/session/admin listener, deployment or operational state.',
        'No SIGKILL restoration claim; no NFS, systemd, bundle/shipping or full release qualification.',
        'Default TTY cases only; stdin JSON, guard/orphan and record-schema cases remain in the separate runtime gates.',
        'No raw terminal/CLI diagnostics, passwords, account bytes or verifier/equality tokens retained.'])
    runner = Runner()
    try:
        helpers = ingress_helpers()
        platform, artifacts, evidence = helpers.load_gate(args.production_gate)
        report['gate'] = evidence  # Every committed Rust blob, including frozen reference inputs.
        sources = ('check-admin-account.py', 'test_admin_account.py', 'check-producer-ingress.py',
                   'nfs_fixture_contract.py', 'check-rust-sles.py', 'rust-platform.json')
        report['driver_sha256'] = {name: hashlib.sha256((ROOT/'scripts'/name).read_bytes()).hexdigest() for name in sources}
        report['spec_sha256'] = hashlib.sha256((ROOT/'docs/ADMIN-ACCOUNT-INCREMENT.md').read_bytes()).hexdigest()
        report['config_template_sha256'] = hashlib.sha256((ROOT/'rust/config/local.example.json').read_bytes()).hexdigest()
        report['git_commit'] = runner.command(['git', 'rev-parse', 'HEAD']).stdout.decode().strip()
        archive, _ = fixture_archive(helpers, artifacts)
        report['fixture_archive_sha256'] = hashlib.sha256(archive).hexdigest()
        report['runtime_image'] = platform['runtime']
        identity = create_container(runner, platform['runtime'])
        runner.command(['podman', 'start', identity])
        report['container'] = identity
        require(runner.command(['podman', 'inspect', '--format', '{{.HostConfig.NetworkMode}}', identity]).stdout.strip() == b'none',
                'fixture networking is not disabled')
        require(runner.execute('getconf', 'GNU_LIBC_VERSION').stdout.strip() == b'glibc 2.22', 'not pinned SLES glibc')
        status = runner.execute('cat', '/proc/self/status').stdout.decode('ascii')
        fields = dict(line.split(':', 1) for line in status.splitlines() if ':' in line)
        require(fields['Uid'].split() == ['1000']*4 and fields['Gid'].split() == ['1001']*4
                and all(int(fields[k], 16) == 0 for k in ('CapInh', 'CapPrm', 'CapEff', 'CapBnd'))
                and fields['NoNewPrivs'].strip() == '1', 'unsafe fixture identity/capabilities')
        report['identity'] = dict(uid=1000, gid=1001, capabilities=0, no_new_privileges=True, network='none')
        # Preflight existing tools and core Perl POSIX support, no installation.
        runner.execute('/bin/sh', '-eu', '-c', 'command -v stty; command -v tty; command -v sha256sum')
        runner.execute('/usr/bin/perl', '-MPOSIX=setpgid,tcsetpgrp,getpgrp', '-e', 'print "ready"')
        # Seekable regular stdin avoids Podman's pipe writer/extractor race.
        with tempfile.TemporaryFile() as transfer:
            transfer.write(archive)
            transfer.seek(0)
            runner.command(['podman', 'cp', '--archive=false', '-', identity+':/tmp'], stdin=transfer, timeout=60)
        for profile in ('debug', 'release'):
            account = '/tmp/ingress/'+profile+'/account'
            require(runner.execute('stat', '-c', '%u:%g:%a', account).stdout.strip() == b'1000:1001:700',
                    'account directory tar custody differs')
            record = dict(profile=profile, binary_sha256=evidence['artifacts'][profile]['sha256'], cases=[], passed=False)
            report['profiles'].append(record)
            run_profile(runner, profile, evidence['artifacts'][profile], record)
        report['status'] = 'PASSED'
    except CheckError as error:
        report['error'] = str(error)  # Only our fixed labels, never captured output.
    except Exception:
        # No traceback or exception text: either could contain a captured secret.
        report['error'] = 'account PTY qualification failed; private capture discarded'
    finally:
        try:
            runner.close()
            report['cleanup'] = dict(passed=True)
        except Exception:
            report['status'] = 'FAILED'
            report['cleanup'] = dict(passed=False)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open('x') as output:
            json.dump(report, output, indent=2)
            output.write('\n')
    print(json.dumps(dict(status=report['status'], report=str(args.report), cleanup=report['cleanup'])))
    return 0 if report['status'] == 'PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
