#!/usr/bin/env python3
"""Qualify protected UDS ingress with retained production SLES artifacts, offline.

Usage: python3 scripts/check-producer-ingress.py --production-gate PATH --report PATH
No build, pull, installation, host account change or operational state access.
Only the created, network-disabled container is changed/removed. PASSED covers
these finite local cases, never TLS, real NFS, systemd, or shipping lifecycle.
"""
import argparse
import base64
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import selectors
import shlex
import subprocess
import tarfile
import time
import traceback

from nfs_fixture_contract import producer_request, validate_producer_response, validate_writer_bytes

ROOT = Path(__file__).resolve().parents[1]
APP_USER = '1000:1001'
PROXY_USER = '1001:1001'
PRINCIPAL = 'X-File-Mover-Generator'

# Stop writing on an early error reply/EPIPE, but still read the complete reply.
# All target clients are actual Unix sockets and real container UIDs, never a
# simulated trusted header or a TCP-to-UDS adapter.
CLIENT = r'''
use strict; use warnings; use Socket; use MIME::Base64;
$SIG{PIPE}='IGNORE'; alarm 12;
socket(my $s,PF_UNIX,SOCK_STREAM,0) or die "socket: $!";
connect($s,sockaddr_un($ARGV[0])) or die "connect: $!";
my $r=decode_base64($ARGV[1]); my $sent=0;
while($sent<length($r)) {
    my $n=syswrite($s,$r,length($r)-$sent,$sent);
    last unless defined($n) && $n>0; $sent+=$n;
}
shutdown($s,1); my $out='';
while(1) {
    my $n=sysread($s,my $b,8192);
    if(!defined($n)) { last if length($out); die "read: $!"; }
    last unless $n; $out.=$b; die 'oversized response' if length($out)>131072;
}
print encode_base64($out,'');
'''

LOST_CLIENT = CLIENT.split("shutdown($s,1); my $out='';", 1)[0] + 'shutdown($s,1); close($s) or die $!;'

SLOW_CLIENTS = r'''
use strict; use warnings; use Socket; use MIME::Base64;
$|=1; $SIG{PIPE}='IGNORE'; alarm 14;
my @s; my $count=$ARGV[1] || 6;
for(1..$count) {
    socket(my $s,PF_UNIX,SOCK_STREAM,0) or die "socket: $!";
    connect($s,sockaddr_un($ARGV[0])) or die "connect: $!";
    my $r="POST /api/v2/jobs HTTP/1.1\r\nHost: localhost\r\n";
    syswrite($s,$r)==length($r) or die 'partial slow write'; push @s,$s;
}
select(undef,undef,undef,0.2); print "READY\n";
for my $s (@s) {
    my $out='';
    while(1) {
        my $n=sysread($s,my $b,8192); die "slow read: $!" unless defined($n);
        last unless $n; $out.=$b; die 'oversized slow response' if length($out)>131072;
    }
    print encode_base64($out,''),"\n";
}
'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def wire(method='POST', path='/api/v2/jobs', body=None, headers=None):
    payload = b'' if body is None else json.dumps(body, separators=(',', ':')).encode()
    fields = [('Host', 'localhost'), ('Connection', 'close'), ('Content-Type', 'application/json'),
              ('Content-Length', str(len(payload)))]
    if headers is not None:
        fields += headers
    return (f'{method} {path} HTTP/1.1\r\n' + ''.join(f'{k}: {v}\r\n' for k, v in fields) + '\r\n').encode() + payload


def parse_reply(raw):
    head, separator, data = raw.partition(b'\r\n\r\n')
    require(separator, 'missing HTTP header terminator')
    lines = head.decode('ascii').split('\r\n')
    require(re.fullmatch(r'HTTP/1\.[01] [0-9]{3}(?: .*)?', lines[0]), 'invalid HTTP status')
    fields = {}
    for line in lines[1:]:
        key, value = line.split(':', 1)
        fields.setdefault(key.lower(), []).append(value.strip())
    require(len(fields.get('content-length', [])) == 1, 'missing/duplicate reply Content-Length')
    require(len(data) == int(fields['content-length'][0]), 'truncated/extra reply bytes')
    return dict(code=int(lines[0].split()[1]), headers=fields, body=json.loads(data))


def rust_git_blobs(root):
    """Read committed bytes directly; Windows checkout CRLF is not provenance."""
    listing = subprocess.run(['git', 'ls-tree', '-rz', 'HEAD', '--', 'rust'], cwd=root,
                             capture_output=True, check=True).stdout
    entries = []
    for row in listing.split(b'\0'):
        if not row:
            continue
        metadata, path = row.split(b'\t', 1)
        mode, kind, oid = metadata.split()
        require(kind == b'blob' and mode in (b'100644', b'100755'), 'nonregular committed Rust input')
        name = path.decode('utf-8')
        require(name.startswith('rust/'), 'unexpected Git source path')
        require(not {'target', 'validation'}.intersection(Path(name).parts), 'generated state committed under Rust sources')
        entries.append((name[5:], oid))
    require(entries, 'no committed Rust source inputs')
    objects = subprocess.run(['git', 'cat-file', '--batch'], cwd=root,
                             input=b''.join(oid+b'\n' for _, oid in entries),
                             capture_output=True, check=True).stdout
    stream = io.BytesIO(objects)
    result = {}
    for name, oid in entries:
        saved_oid, kind, size = stream.readline().split()
        require(saved_oid == oid and kind == b'blob', 'Git object framing mismatch')
        data = stream.read(int(size))
        require(len(data) == int(size) and stream.read(1) == b'\n', 'truncated Git blob')
        result[name] = data
    require(not stream.read(), 'extra Git object bytes')
    return result


def load_gate(folder, root=ROOT):
    """Bind the passed gate, current Rust source, actual ELF and both app hashes."""
    folder = folder.resolve(strict=True)
    report_bytes = (folder/'report.json').read_bytes()
    gate = json.loads(report_bytes)
    config = json.loads((root/'scripts/rust-platform.json').read_bytes())
    require(gate['status'] == 'PASSED' and not gate.get('cleanup_error'), 'production gate did not pass/clean up')
    require(gate['build_mode'] == 'production' and gate['config'] == config, 'wrong gate mode/platform')
    require('@sha256:' in config['runtime'], 'runtime is not digest-pinned')
    archive = (folder/'source.tar.gz').read_bytes()
    require(sha(archive) == gate['source_sha256'], 'gate source archive hash mismatch')
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
        members = tar.getmembers()
        require(all(m.isfile() or m.isdir() for m in members), 'source archive has aliases/foreign types')
        names = [m.name for m in members if m.isfile()]
        require(len(names) == len(set(names)), 'duplicate source members')
        saved = {m.name: tar.extractfile(m).read() for m in members if m.isfile()}
    current = rust_git_blobs(root)
    require(saved == current, 'gate source differs from committed Rust Git blobs')
    spec = importlib.util.spec_from_file_location('ingress_sles_audit', root/'scripts/check-rust-sles.py')
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    artifacts = {}
    evidence = dict(run_id=gate['run_id'], report_sha256=sha(report_bytes), source_sha256=sha(archive),
                    source_basis='HEAD Git blobs; checkout line endings are not compared',
                    rust_inputs={n: sha(data) for n, data in sorted(current.items())}, artifacts={})
    for profile in ('debug', 'release'):
        require(gate['profiles'][profile]['tests_passed'] > 0, 'gate lacks passed target tests')
        apps = [a for a in gate['profiles'][profile]['artifacts'] if not a['test']]
        require(len(apps) == 1 and apps[0]['name'].startswith(profile+'-') and apps[0]['name'].endswith('-file-mover'),
                'expected exactly one production file-mover app per profile')
        item = apps[0]
        require(Path(item['name']).name == item['name'], 'unsafe artifact name')
        path = folder/item['name']
        require(sha(path.read_bytes()) == item['sha256'], 'app artifact hash mismatch')
        elf = (folder/(item['name']+'.elf')).read_bytes()
        require(audit.audit(elf.decode()) == item['elf'], 'retained ELF audit mismatch')
        artifacts[profile] = path
        evidence['artifacts'][profile] = dict(item, elf_sha256=sha(elf))
    return config, artifacts, evidence


def fixture_archive(artifacts):
    """Numeric tar ownership needs no CHOWN/DAC capability inside the container."""
    config_template = json.loads((ROOT/'rust/config/local.example.json').read_bytes())
    configs = {}
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as tar:
        def add(name, mode, data=None):
            info = tarfile.TarInfo(name)
            info.uid, info.gid, info.mode = 1000, 1001, mode
            info.type = tarfile.DIRTYPE if data is None else tarfile.REGTYPE
            if data is not None:
                info.size = len(data)
            tar.addfile(info, None if data is None else io.BytesIO(data))
        add('ingress', 0o711)
        for profile in ('debug', 'release'):
            prefix = 'ingress/'+profile
            base = '/tmp/'+prefix
            for name, mode in (('', 0o711), ('/p', 0o750), ('/state', 0o700), ('/operator', 0o700),
                               ('/source', 0o700), ('/source/.file-mover', 0o700), ('/source/current', 0o700),
                               ('/destination', 0o700), ('/destination/.file-mover', 0o700)):
                add(prefix+name, mode)
            config = copy.deepcopy(config_template)
            config.update(bind='127.0.0.1:19879', generator_id='fixture', source_root=base+'/source',
                          destination_root=base+'/destination', state_database=base+'/state/jobs.sqlite',
                          check_expected_sizes=True,
                          protected_ingress=dict(producer_socket=base+'/p/in.sock', operator_socket=base+'/operator/in.sock',
                                                 proxy_uid=1001, proxy_gid=1001))
            for endpoint in ('producer_socket', 'operator_socket'):
                require(len(config['protected_ingress'][endpoint].encode()) <= 107, 'UDS pathname exceeds Linux bound')
            configs[profile] = config
            add(prefix+'/config.json', 0o600, json.dumps(config).encode())
            add(prefix+'/file-mover', 0o500, artifacts[profile].read_bytes())
            for role in ('source', 'destination'):
                add(prefix+f'/{role}/.file-mover/{role}-binding.json', 0o600, json.dumps(config[role+'_binding']).encode())
                add(prefix+f'/{role}/.file-mover/coordinator.lock', 0o600, b'')
            add(prefix+'/source/current/a', 0o600, b'ingress payload A')
            add(prefix+'/source/current/b', 0o600, b'ingress payload B')
    return buffer.getvalue(), configs


class Runner:
    def __init__(self, report):
        self.report, self.container = report, None
        self.processes = []

    def command(self, args, ok=True, timeout=20, data=None):
        result = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
        if ok and result.returncode:
            raise RuntimeError(f'{args[:4]}: {result.returncode}: {result.stderr.decode(errors="replace")[-2000:]}')
        return result

    def execute(self, *args, user=APP_USER, ok=True, timeout=20):
        return self.command(['podman', 'exec', '--user', user, self.container, '/usr/bin/setsid', '--wait', *args], ok, timeout)

    def shell(self, script, **kwargs):
        return self.execute('/bin/sh', '-eu', '-c', script, **kwargs)

    def spawn(self, *args, user=APP_USER):
        process = subprocess.Popen(['podman', 'exec', '--user', user, self.container,
                                    '/usr/bin/setsid', '--wait', *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.processes.append(process)
        return process

    def http(self, endpoint, raw, user=PROXY_USER):
        started = time.monotonic()
        result = self.execute('/usr/bin/perl', '-e', CLIENT, endpoint, base64.b64encode(raw).decode(),
                              user=user, ok=False, timeout=15)
        record = dict(user=user, request_base64=base64.b64encode(raw).decode(), endpoint=endpoint,
                      exit_code=result.returncode, stderr=result.stderr.decode(errors='replace'),
                      seconds=round(time.monotonic()-started, 4))
        if result.returncode == 0:
            reply = base64.b64decode(result.stdout, validate=True)
            record['raw_base64'] = base64.b64encode(reply).decode()
            if reply:
                record.update(parse_reply(reply))
        self.report['requests'].append(record)
        return record

    def close(self):
        cleanup_ok = True
        if self.container:
            result = self.command(['podman', 'rm', '-f', self.container], ok=False)
            self.report['cleanup'] = dict(exit_code=result.returncode, stdout=result.stdout.decode(errors='replace'),
                                          stderr=result.stderr.decode(errors='replace'))
            cleanup_ok = result.returncode == 0
        for process in self.processes:
            if process.poll() is None:
                process.terminate()  # Only the host CLI process we created, by its PID.
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)
        require(cleanup_ok, 'owned container cleanup failed')


def wait_until(check, message, seconds=12):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.1)
    raise AssertionError(message)


def error_reply(row, code, errors):
    require(row.get('code') == code, f'expected {code}, got {row}')
    body = row['body']
    require(set(body) == {'recording_id', 'error', 'retryable', 'retry_after_seconds', 'source_paths_released'}, 'noncanonical producer error')
    require(body['error'] in errors and body['source_paths_released'] is False, 'wrong error/release meaning')
    require(type(body['retryable']) is bool, 'invalid retryable field')
    delay = body['retry_after_seconds']
    require(delay is None or (type(delay) is int and 1 <= delay <= 2147483647), 'invalid retry delay')
    if code in (400, 403, 405, 413, 431):
        require(body['retryable'] is False and delay is None, 'permanent refusal offered automatic retry')
    require(body['recording_id'] is None or re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', body['recording_id']), 'bad error UUID')
    return body


def run_profile(runner, profile, config, artifact_sha):
    base = '/tmp/ingress/'+profile
    binary, config_path = base+'/file-mover', base+'/config.json'
    producer, operator = [config['protected_ingress'][k] for k in ('producer_socket', 'operator_socket')]
    principal = [(PRINCIPAL, config['generator_id'])]
    report = dict(profile=profile, binary_sha256=artifact_sha, config=config, passed=False, unsafe_cases=[])
    runner.report['profiles'].append(report)
    q = shlex.quote

    def control(action, ok=True):
        start = time.monotonic()
        result = runner.execute(binary, action, config_path, ok=ok, timeout=8)
        row = dict(action=action, exit_code=result.returncode, stdout=result.stdout.decode(errors='replace'),
                   stderr=result.stderr.decode(errors='replace'), seconds=round(time.monotonic()-start, 4))
        report.setdefault('control', []).append(row)
        return row

    def launch(path=config_path):
        return runner.spawn('/bin/sh', '-eu', '-c', f'echo $$ >{base}/state/app.pid; exec {binary} {q(path)} >{base}/state/service.log 2>&1')

    def ready(process):
        def check():
            require(process.poll() is None, 'service exited before readiness')
            return b'Ready on protected' in runner.execute('cat', base+'/state/service.log').stdout
        wait_until(check, 'missing protected readiness')
        require(runner.http(operator, wire('GET', '/healthz'), APP_USER).get('code') == 200, 'private health unavailable')

    def stop(process):
        result = control('--stop')
        require(json.loads(result['stdout'])['phase'] == 'Stopped', 'stop did not complete')
        process.communicate(timeout=8)
        require(process.returncode == 0, 'service failed clean shutdown')
        runner.execute('test', '!', '-e', producer)
        runner.execute('test', '!', '-e', operator)

    def stable_files():
        # Quiescent fixture only. Do not open SQLite: hash its stopped DB/WAL.
        text = runner.shell(f'find {base}/source {base}/destination -type f -exec sha256sum {{}} +; '
                            f'find {base}/state -maxdepth 1 -type f -name "jobs.sqlite*" -exec sha256sum {{}} +').stdout
        return sorted(text.decode().splitlines())

    def no_tcp():
        probe = r'use Socket; socket(my $s,PF_INET,SOCK_STREAM,0) or die $!; alarm 2; exit(connect($s,sockaddr_in(19879,inet_aton("127.0.0.1"))) ? 1 : 0);'
        runner.execute('/usr/bin/perl', '-e', probe, user=PROXY_USER)
        # No TCP listeners at any address/port in this isolated network namespace.
        inventory = runner.execute('cat', '/proc/net/tcp', '/proc/net/tcp6').stdout.decode()
        require(not any(len(line.split()) > 3 and line.split()[3] == '0A' for line in inventory.splitlines()), 'protected mode left a TCP listener')
        report['tcp_inventory'] = inventory

    require(runner.execute('sha256sum', binary).stdout.decode().split()[0] == artifact_sha, 'container executable differs from gate')
    report['ldd'] = runner.execute('ldd', '-r', binary).stdout.decode()
    require('not found' not in report['ldd'] and 'undefined symbol' not in report['ldd'], 'runtime relocation failure')
    require('build=production' in runner.execute(binary, '--check-platform').stdout.decode(), 'not a production binary')
    # Explicitly prove preprovisioned owner/mode/group, not merely successful connect.
    expected = [(base, '1000:1001:711'), (base+'/p', '1000:1001:750'),
                (base+'/state', '1000:1001:700'), (base+'/operator', '1000:1001:700')]
    report['parents'] = {}
    for path, metadata in expected:
        value = runner.execute('stat', '-c', '%u:%g:%a', path).stdout.decode().strip()
        require(value == metadata, 'preprovisioned directory ownership/mode prerequisite failed: '+path)
        report['parents'][path] = value
    runner.execute(binary, '--initialize-source', config_path)
    enrollment = runner.execute('cat', base+'/source/.file-mover/source-enrollment.json').stdout
    process = launch()
    ready(process)
    no_tcp()
    for endpoint, mode in ((producer, '660'), (operator, '600')):
        metadata = runner.execute('stat', '-c', '%u:%g:%a:%F', endpoint).stdout.decode().strip()
        require(metadata == '1000:1001:'+mode+':socket', 'wrong socket custody: '+metadata)
    for user in (PROXY_USER, '1002:1001', '0:1001'):
        row = runner.http(operator, wire('GET', '/healthz'), user)
        require(row.get('code') is None and (row['exit_code'] != 0 or row.get('raw_base64') == ''),
                'foreign UID received an operator HTTP reply')
    # Wrong peers must be refused even for incomplete/invalid HTTP, before parsing.
    for user in ('1002:1001', '0:1001'):
        row = runner.http(producer, b'not HTTP', user)
        error_reply(row, 403, {'caller_not_authorized'})
        require(row['seconds'] < 3, 'wrong-peer refusal waited for HTTP read deadline')

    request = producer_request(base+'/source/current', {'a': len(b'ingress payload A'), 'b': len(b'ingress payload B')})
    report['submission'] = request
    # Submit once and deliberately read no response. Prove that request reached
    # durable custody before the next POST, then recover its original receipt.
    lost_raw = wire(body=request, headers=principal)
    lost = runner.execute('/usr/bin/perl', '-e', LOST_CLIENT, producer,
                          base64.b64encode(lost_raw).decode(), user=PROXY_USER)
    report['lost_response'] = dict(exit_code=lost.returncode, read_response=False,
                                  request_base64=base64.b64encode(lost_raw).decode())
    def lost_handoff():
        row = runner.http(operator, wire('GET', '/api/v2/jobs/1'), APP_USER)
        return row.get('code') == 200 and row['body'].get('source_paths_released') is True
    wait_until(lost_handoff, 'unread-response request did not establish durable handoff', seconds=20)
    accepted = runner.http(producer, wire(body=request, headers=principal))
    require(accepted.get('code') == 202, 'actual protected handoff did not succeed')
    validate_producer_response(202, accepted['body'], request)
    job = accepted['body']['job_id']
    report['accepted'] = accepted['body']
    def committed():
        row = runner.http(operator, wire('GET', '/api/v2/jobs/'+job), APP_USER)
        return row.get('code') == 200 and row['body'].get('state') == 'Committed'
    wait_until(committed, 'protected recording never committed', seconds=20)
    area = base+'/destination/'+request['recording_id']
    manifest_bytes = runner.execute('cat', area+'/COMMITTED.json').stdout
    manifest = validate_writer_bytes(manifest_bytes, request)
    require(manifest['job_id'] == job, 'manifest job identity differs from receipt')
    for index, name in enumerate(request['files']):
        payload = b'ingress payload '+name.upper().encode()
        require(runner.execute('cat', area+'/'+name).stdout == payload, 'destination payload changed')
        require(runner.execute('cat', base+'/source/.file-mover/'+job+'-'+str(index)+'/data').stdout == payload, 'numeric private claim changed')
        require(manifest['files'][index]['size_bytes'] == str(len(payload)) and manifest['files'][index]['sha256'] == sha(payload), 'manifest measured content mismatch')
    report['manifest_base64'], report['manifest_sha256'] = base64.b64encode(manifest_bytes).decode(), sha(manifest_bytes)
    runner.shell(f"printf 'producer reuse A' >{base}/source/current/a; printf 'producer reuse B' >{base}/source/current/b")
    def preserved_reused_and_owned_files():
        for index, name in enumerate(request['files']):
            suffix = name.upper().encode()
            require(runner.execute('cat', base+'/source/current/'+name).stdout == b'producer reuse '+suffix,
                    'replay modified a producer-reused leaf')
            original = b'ingress payload '+suffix
            require(runner.execute('cat', base+'/source/.file-mover/'+job+'-'+str(index)+'/data').stdout == original,
                    'replay modified original private custody')
            require(runner.execute('cat', area+'/'+name).stdout == original,
                    'replay modified original destination output')
    reordered = copy.deepcopy(request)
    reordered['files'].reverse()
    for body in (request, reordered):
        replay = runner.http(producer, wire(body=body, headers=principal))
        require(replay.get('code') == 202 and replay['body'] == accepted['body'], 'release replay changed under producer path reuse/permutation')
    require(runner.execute('cat', area+'/COMMITTED.json').stdout == manifest_bytes, 'replay rewrote immutable manifest bytes')
    preserved_reused_and_owned_files()

    # A changed body is paired with a known UUID to test authorization before replay.
    wrong_generator = dict(request, generator_id='spoofed')
    for headers, body in (([], request), ([(PRINCIPAL, 'spoofed')], request), (principal, wrong_generator)):
        error_reply(runner.http(producer, wire(body=body, headers=headers)), 403, {'caller_not_authorized', 'unknown_generator'})
    error_reply(runner.http(producer, wire(body=request, headers=principal+principal)), 400, {'invalid_http'})
    # A missing principal must win over body JSON parsing on a valid HTTP head.
    error_reply(runner.http(producer, wire()), 403, {'caller_not_authorized'})
    for path in ('/healthz', '/api/v2/jobs/'+job, '/api/v2/jobs/99999', '/api/v2/retention', '/api/v2/jobs?x=1', '/api/v2/jobs/'):
        row = runner.http(producer, wire('GET', path, headers=principal))
        error_reply(row, 403, {'producer_route_forbidden'})
        require(row['body']['recording_id'] is None, 'forbidden route disclosed a recording')
    method = runner.http(producer, wire('GET', '/api/v2/jobs', headers=principal))
    error_reply(method, 405, {'method_not_allowed'})
    require(method['headers'].get('allow') == ['POST'], 'wrong/missing producer Allow')
    operator_submit = runner.http(operator, wire(body=request, headers=principal), APP_USER)
    require(operator_submit.get('code') == 404 and operator_submit['body'] ==
            {'error': 'not_found', 'source_paths_released': False, 'retryable': False},
            'operator transport admitted a producer submission')
    # Framing/body limits remain enforced after peer and principal authorization.
    for raw, code, errors in (
        (wire(headers=principal+[('Content-Length', '0')]), 400, {'invalid_http'}),
        (wire(headers=principal+[('Transfer-Encoding', 'chunked')]), 400, {'invalid_http', 'unsupported_headers'}),
        (wire(headers=principal+[('X-Pad', 'x'*8192)]), 431, {'request_headers_too_large'}),
        (wire(headers=principal+[(f'X-{i}', 'x') for i in range(65)]), 400, {'invalid_http'}),
        (wire(headers=principal).replace(b'Content-Length: 0', b'Content-Length: 65537'), 413, {'request_too_large'})):
        error_reply(runner.http(producer, raw), code, errors)
    require(runner.http(operator, wire('GET', '/api/v2/jobs/'+str(int(job)+1)), APP_USER).get('code') == 404, 'denial allocated a new job')
    retention = runner.http(operator, wire('GET', '/api/v2/retention'), APP_USER)
    require(retention.get('code') == 200 and retention['body']['details']['retained_jobs'] == 1, 'refusal changed retained job count')

    slow = runner.spawn('/usr/bin/perl', '-e', SLOW_CLIENTS, producer, user=PROXY_USER)
    began = time.monotonic()
    with selectors.DefaultSelector() as selector:
        selector.register(slow.stdout, selectors.EVENT_READ)
        require(selector.select(timeout=3), 'six slow producer clients failed to start')
        require(slow.stdout.readline() == b'READY\n', 'slow client connection failure')
    # Occupy one local HTTP slot as the mover; health must still use the second.
    slow_operator = runner.spawn('/usr/bin/perl', '-e', SLOW_CLIENTS, operator, '1', user=APP_USER)
    with selectors.DefaultSelector() as selector:
        selector.register(slow_operator.stdout, selectors.EVENT_READ)
        require(selector.select(timeout=3), 'slow operator client failed to start')
        require(slow_operator.stdout.readline() == b'READY\n', 'slow operator connection failure')
    excess = runner.http(producer, wire(body=request, headers=principal))
    error_reply(excess, 429, {'rate_limited'})
    require(excess['headers'].get('retry-after') == ['1'] and excess['body']['retry_after_seconds'] == 1 and excess['body']['retryable'] is True, 'saturation lacks one-second retry guidance')
    health = runner.http(operator, wire('GET', '/healthz'), APP_USER)
    require(health.get('code') == 200 and health['seconds'] < 3, 'reserved operator slot was blocked by producers')
    status = control('--status')
    require(status['seconds'] < 3 and json.loads(status['stdout'])['phase'] == 'Running', 'independent control blocked by producers')
    stdout, stderr = slow.communicate(timeout=12)
    require(slow.returncode == 0, 'slow client failed: '+stderr.decode(errors='replace'))
    rows = [parse_reply(base64.b64decode(line, validate=True)) for line in stdout.splitlines()]
    require(len(rows) == 6 and all(row['code'] == 408 and row['body']['error'] == 'request_timeout' for row in rows), 'six read slots did not expire under the existing deadline')
    op_stdout, op_stderr = slow_operator.communicate(timeout=8)
    require(slow_operator.returncode == 0, 'slow operator client failed: '+op_stderr.decode(errors='replace'))
    op_rows = [parse_reply(base64.b64decode(line, validate=True)) for line in op_stdout.splitlines()]
    require(len(op_rows) == 1 and op_rows[0]['code'] == 408, 'reserved slow operator slot did not time out')
    require(time.monotonic()-began < 9, 'slow connections outlived bounded read window')
    report['saturation'] = dict(excess=excess, health=health, control=status, slow=rows, slow_operator=op_rows, seconds=round(time.monotonic()-began, 4))
    stop(process)
    require(runner.execute('cat', base+'/source/.file-mover/source-enrollment.json').stdout == enrollment, 'original enrollment changed')
    process = launch()
    ready(process)
    no_tcp()
    replay = runner.http(producer, wire(body=reordered, headers=principal))
    require(replay.get('code') == 202 and replay['body'] == accepted['body'], 'clean restart lost original UUID receipt')
    require(runner.execute('cat', area+'/COMMITTED.json').stdout == manifest_bytes, 'restart regenerated manifest')
    preserved_reused_and_owned_files()
    stop(process)

    # Preexisting endpoint names are never removed, including actual stale sockets.
    before = stable_files()
    for role, parent in (('producer_socket', base+'/p'), ('operator_socket', base+'/operator')):
        for kind in ('file', 'symlink', 'stale', 'live'):
            endpoint = parent+'/existing-'+kind
            modified = copy.deepcopy(config)
            modified['protected_ingress'][role] = endpoint
            path = base+'/state/refusal.json'
            runner.shell('printf %s '+q(json.dumps(modified))+' >'+path)
            if kind == 'file':
                runner.shell('set -C; printf sentinel >'+endpoint)
            elif kind == 'symlink':
                runner.execute('ln', '-s', base+'/source/current/a', endpoint)
            elif kind == 'stale':
                runner.execute('/usr/bin/perl', '-MSocket', '-e', 'socket(my $s,PF_UNIX,SOCK_STREAM,0) or die $!; bind($s,sockaddr_un($ARGV[0])) or die $!;', endpoint)
            else:
                live = runner.spawn('/usr/bin/perl', '-MSocket', '-e',
                    '$|=1; alarm 18; socket(my $s,PF_UNIX,SOCK_STREAM,0) or die $!; '
                    'bind($s,sockaddr_un($ARGV[0])) or die $!; listen($s,1) or die $!; '
                    'print $$,chr(10); select(undef,undef,undef,16);', endpoint)
                with selectors.DefaultSelector() as selector:
                    selector.register(live.stdout, selectors.EVENT_READ)
                    require(selector.select(timeout=3), 'fixture live socket failed to bind')
                    live_pid = live.stdout.readline().decode().strip()
                    require(live_pid.isdigit(), 'invalid fixture listener PID')

            identity = runner.execute('stat', '-c', '%d:%i:%F:%u:%g:%a', endpoint).stdout
            refused = launch(path)
            out, err = refused.communicate(timeout=8)
            require(refused.returncode != 0, 'existing endpoint admitted: '+role+'/'+kind)
            require(runner.execute('stat', '-c', '%d:%i:%F:%u:%g:%a', endpoint).stdout == identity, 'refusal replaced existing endpoint')
            if kind == 'file':
                require(runner.execute('cat', endpoint).stdout == b'sentinel', 'existing endpoint bytes changed')
            runner.execute('test', '!', '-e', producer)
            runner.execute('test', '!', '-e', operator)
            require(stable_files() == before, 'unsafe endpoint startup changed original source/destination/SQLite')
            if kind == 'live':
                runner.execute('kill', '-TERM', live_pid)  # Exact PID reported by our helper in our container.
                live.communicate(timeout=3)
            report['unsafe_cases'].append(dict(role=role, kind=kind, identity=identity.decode(), exit_code=refused.returncode,
                                               log=runner.execute('cat', base+'/state/service.log').stdout.decode(errors='replace')))
    for kind in ('missing-parent', 'writable-parent', 'symlink-parent'):
        modified = copy.deepcopy(config)
        if kind == 'missing-parent':
            modified['protected_ingress']['producer_socket'] = base+'/missing/in.sock'
        elif kind == 'writable-parent':
            runner.execute('chmod', '0770', base+'/p')
        else:
            runner.execute('ln', '-s', base+'/p', base+'/alias')
            modified['protected_ingress']['producer_socket'] = base+'/alias/in.sock'
        path = base+'/state/refusal.json'
        runner.shell('printf %s '+q(json.dumps(modified))+' >'+path)
        refused = launch(path)
        refused.communicate(timeout=8)
        require(refused.returncode != 0 and stable_files() == before, 'unsafe parent admitted/changed original state: '+kind)
        runner.execute('test', '!', '-e', producer)
        runner.execute('test', '!', '-e', operator)
        if kind == 'writable-parent':
            runner.execute('chmod', '0750', base+'/p')  # Restore only our preprovisioned fixture directory.
        report['unsafe_cases'].append(dict(kind=kind, exit_code=refused.returncode,
                                           log=runner.execute('cat', base+'/state/service.log').stdout.decode(errors='replace')))

    # Move only our own live endpoint, substitute a file, then stop via control.
    # Cleanup must preserve that replacement rather than blindly unlinking it.
    process = launch()
    ready(process)
    original = runner.execute('stat', '-c', '%d:%i', producer).stdout.decode().strip()
    runner.execute('mv', producer, producer+'.owned')
    runner.shell('set -C; printf replacement >'+producer)
    replacement = runner.execute('stat', '-c', '%d:%i', producer).stdout.decode().strip()
    require(replacement != original, 'substitution failed to change endpoint inode')
    control('--stop', ok=False)
    process.communicate(timeout=8)
    require(runner.execute('cat', producer).stdout == b'replacement', 'shutdown unlinked/replaced substituted endpoint')
    require(runner.execute('stat', '-c', '%d:%i', producer).stdout.decode().strip() == replacement, 'substituted inode changed')
    require(runner.execute('stat', '-c', '%d:%i', producer+'.owned').stdout.decode().strip() == original, 'cleanup touched renamed owned socket')
    require(stable_files() == before, 'socket substitution shutdown changed original state')
    report['substitution'] = dict(original=original, replacement=replacement, app_exit_code=process.returncode,
                                  replacement_preserved=True, renamed_socket_preserved=True)
    report['passed'] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production-gate', required=True, type=Path, help='retained PASSED check-rust-sles production directory')
    parser.add_argument('--report', required=True, type=Path, help='new report path; existing evidence never overwritten')
    args = parser.parse_args()
    require(not args.report.exists(), 'report already exists; choose a new evidence path')
    report = dict(status='FAILED', profiles=[], requests=[], limits=[
        'Finite disposable local SLES/UDS qualification only; no TLS, real proxy, auth deployment, NFS or systemd.',
        'No legacy lifecycle fixture, actual crash recovery, or listener-FD worker audit in this bounded pass.',
        'Stale socket creation tests refusal, never automatic stale cleanup or repair.'])
    runner = Runner(report)
    try:
        platform, artifacts, evidence = load_gate(args.production_gate)
        report['gate'] = evidence
        sources = ('check-producer-ingress.py', 'nfs_fixture_contract.py', 'check-rust-sles.py', 'rust-platform.json')
        report['driver_sha256'] = {name: sha((ROOT/'scripts'/name).read_bytes()) for name in sources}
        report['config_template_sha256'] = sha((ROOT/'rust/config/local.example.json').read_bytes())
        report['git_commit'] = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        archive, configs = fixture_archive(artifacts)
        report['fixture_archive_sha256'] = sha(archive)
        runner.container = runner.command(['podman', 'create', '--pull=never', '--network', 'none', '--cap-drop', 'all',
            '--security-opt', 'no-new-privileges', '--entrypoint', '/bin/sh', platform['runtime'], '-c', 'exec sleep infinity']).stdout.decode().strip()
        report['container'] = runner.container
        runner.command(['podman', 'start', runner.container])
        report['runtime_image'] = json.loads(runner.command(['podman', 'image', 'inspect', platform['runtime']]).stdout)
        network = runner.command(['podman', 'inspect', '--format', '{{.HostConfig.NetworkMode}}', runner.container]).stdout.decode().strip()
        require(network == 'none', 'fixture has external networking')
        report['network'] = network
        require(runner.execute('getconf', 'GNU_LIBC_VERSION').stdout.strip() == b'glibc 2.22', 'not pinned glibc 2.22 runtime')
        runner.execute('/usr/bin/perl', '-MSocket', '-MMIME::Base64', '-e', 'print "ready"')
        # Engine-side tar copy preserves numeric ownership with zero target capabilities.
        runner.command(['podman', 'cp', '--archive=true', '-', runner.container+':/tmp'], data=archive)
        report['identities'] = {}
        for user in (APP_USER, PROXY_USER, '1002:1001', '0:1001'):
            row = runner.execute('cat', '/proc/self/status', user=user).stdout.decode()
            fields = dict(line.split(':', 1) for line in row.splitlines() if ':' in line)
            uid, gid = user.split(':')
            require(fields['Uid'].split() == [uid]*4 and fields['Gid'].split() == [gid]*4, 'OCI exec identity differs from requested peer')
            require(all(int(fields[key], 16) == 0 for key in ('CapInh', 'CapPrm', 'CapEff', 'CapBnd')), 'peer has capabilities')
            require(fields['NoNewPrivs'].strip() == '1', 'peer can gain privileges')
            report['identities'][user] = row
        for profile in ('debug', 'release'):
            print('Protected producer ingress: '+profile, flush=True)
            run_profile(runner, profile, configs[profile], evidence['artifacts'][profile]['sha256'])
        report['status'] = 'PASSED'
    except Exception:
        report['error'] = traceback.format_exc()
        if runner.container:
            report['failure_logs'] = {}
            for profile in ('debug', 'release'):
                try:
                    result = runner.execute('cat', '/tmp/ingress/'+profile+'/state/service.log', ok=False, timeout=3)
                    report['failure_logs'][profile] = result.stdout.decode(errors='replace')[-8000:]
                except Exception as error:
                    report['failure_logs'][profile] = str(error)
    finally:
        try:
            runner.close()
        except Exception:
            report['status'] = 'FAILED'
            report['cleanup_error'] = traceback.format_exc()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open('x') as file:
            json.dump(report, file, indent=2)
            file.write('\n')
    print(json.dumps(dict(status=report['status'], report=str(args.report), error=report.get('error'), cleanup_error=report.get('cleanup_error')), indent=2))
    return 0 if report['status'] == 'PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
