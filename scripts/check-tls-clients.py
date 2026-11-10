#!/usr/bin/env python3
"""Independent curl/OpenSSL clients against retained production SLES binaries.

No builds, pulls, installations or operational state. Creates only an owned
internal container network, two disposable containers, credentials and fixtures.
The report never contains private keys or TLS session output. Existing reports
refuse. Both retained debug/release profiles must pass; cleanup is mandatory.
"""
import argparse
import base64
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import selectors
import shlex
import subprocess
import tarfile
import tempfile
import time
import traceback
import uuid

from nfs_fixture_contract import producer_request, validate_producer_response, validate_writer_bytes
import tls_proof_fixture
from tls_client_tools import curl_args, openssl_args, parse_curl, parse_http

ROOT = Path(__file__).resolve().parents[1]
PORT = 19879
USER = '1000:1001'
PAYLOADS = {'nested/a.bin': b'independent TLS alpha\x00\xff\n', 'b.bin': b'independent TLS bravo\n'}
REUSED = {name: b'new producer bytes '+name.encode() for name in PAYLOADS}


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


ingress = module('tls_ingress_tools', ROOT/'scripts/check-producer-ingress.py')
require = ingress.require
sha = ingress.sha


def bounded_client(command, data=None, timeout=15, discard=False):
    """Drain both pipes with hard byte/time bounds; kill only our CLI PID."""
    process = subprocess.Popen(command, stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL if discard else subprocess.PIPE, stderr=subprocess.PIPE)
    captured = {'stdout': bytearray(), 'stderr': bytearray()}
    deadline, sent = time.monotonic()+timeout, 0
    try:
        with selectors.DefaultSelector() as selector:
            for name, stream in [('stdout', process.stdout), ('stderr', process.stderr)]:
                if stream is not None:
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, selectors.EVENT_READ, name)
            if data is not None:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE, 'stdin')
            while selector.get_map():
                remaining = deadline-time.monotonic()
                require(remaining > 0, 'client process deadline expired')
                for key, _ in selector.select(min(0.2, remaining)):
                    if key.data == 'stdin':
                        try:
                            sent += os.write(key.fd, data[sent:sent+4096])
                        except BrokenPipeError:
                            sent = len(data)
                        if sent == len(data):
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                    else:
                        chunk = os.read(key.fd, 8192)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                            continue
                        captured[key.data] += chunk
                        require(len(captured[key.data]) <= (16384 if key.data == 'stderr' else 131072),
                                'client output exceeds bound')
            process.wait(timeout=max(0.01, deadline-time.monotonic()))
        return subprocess.CompletedProcess(command, process.returncode, bytes(captured['stdout']), bytes(captured['stderr']))
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()


def diagnostics(data):
    require(len(data) <= 16384 and not re.search(
        rb'PRIVATE KEY|CLIENT_RANDOM|TRAFFIC_SECRET|Master-Key:|Resumption PSK:|SSL-Session:|Session-ID:', data),
        'unexpected sensitive client diagnostics')
    return data.decode(errors='replace')


def archive(entries):
    """All entries are explicit regular files/directories, privately owned."""
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w', format=tarfile.USTAR_FORMAT) as tar:
        for name, mode, data in entries:
            require(not name.startswith('/') and '..' not in Path(name).parts, 'unsafe fixture member')
            info = tarfile.TarInfo(name)
            info.uid, info.gid, info.mode = 1000, 1001, mode
            info.type = tarfile.DIRTYPE if data is None else tarfile.REGTYPE
            if data is not None:
                info.size = len(data)
            tar.addfile(info, None if data is None else io.BytesIO(data))
        end = tar.offset
    result = output.getvalue()
    require(result[end:] == bytes(len(result)-end), 'nonzero tar trailer')
    return result[:end+1024]


def fixtures(artifacts, der):
    server = [('tls-interop', 0o711, None)]
    client = [('tls-interop', 0o711, None)]
    configs = {}
    for profile, executable in artifacts.items():
        prefix = 'tls-interop/'+profile
        base = '/tmp/'+prefix
        for suffix in ('', '/state', '/operator', '/credentials', '/source',
                       '/source/.file-mover', '/source/current', '/source/current/nested',
                       '/destination', '/destination/.file-mover'):
            server.append((prefix+suffix, 0o711 if not suffix else 0o700, None))
        client += [(prefix, 0o700, None), (prefix+'/credentials', 0o700, None)]
        config = json.loads((ROOT/'rust/config/local.example.json').read_bytes())
        config.pop('protected_ingress', None)
        config.update(bind=f'0.0.0.0:{PORT}', source_root=base+'/source',
                      destination_root=base+'/destination', state_database=base+'/state/jobs.sqlite',
                      generator_id='fixture', check_expected_sizes=True, shutdown_wait_seconds=5)
        config['native_ingress'] = dict(transport='https', operator_socket=base+'/operator/api.sock',
            authority=f'localhost:{PORT}', server_certificates=[base+'/credentials/server.der'],
            server_key=base+'/credentials/server.key.der', server_ca_certificates=[base+'/credentials/ca.der'],
            client_ca_certificates=[base+'/credentials/ca.der'],
            clients=[dict(sha256=sha(der['client.der']), generator_id='fixture')])
        configs[profile] = config
        server += [(prefix+'/config.json', 0o600, json.dumps(config).encode()),
                   (prefix+'/file-mover', 0o500, executable.read_bytes())]
        for role in ('source', 'destination'):
            server += [(prefix+f'/{role}/.file-mover/coordinator.lock', 0o600, b''),
                       (prefix+f'/{role}/.file-mover/{role}-binding.json', 0o600,
                        json.dumps(config[role+'_binding']).encode())]
        for name, data in PAYLOADS.items():
            server.append((prefix+'/source/current/'+name, 0o600, data))
        for name in ('ca.der', 'other-ca.der', 'server.der', 'server.key.der', 'replacement-server.der', 'replacement-server.key.der'):
            server.append((prefix+'/credentials/'+name, 0o600 if '.key.' in name else 0o400, der[name]))
        server.append((prefix+'/credentials/invalid.key.der', 0o600, b'not a PKCS8 key'))
        for name, data in der.items():
            if name in ('ca.der', 'other-ca.der') or 'client' in name:
                client.append((prefix+'/credentials/'+name, 0o600, data))
    return archive(server), archive(client), configs


def tls_rejection(row):
    """Only explicit certificate-alert failures qualify, never timeout/empty TCP."""
    # libcurl can map a peer's certificate-expired alert to generic code60.
    # Require its actual INCOMING alert; an outgoing local-verification alert
    # or generic verification message cannot establish server-side rejection.
    named = re.search(r'\(IN\), TLS alert,[^\r\n]*(?:certificate|unknown ca|handshake failure|access denied)',
                      row['stderr'], re.IGNORECASE)
    # curl7.88 prints certificate_required as "unknown (628)" in its
    # direction trace; OpenSSL's accompanying peer-alert decode names it.
    required = (re.search(r'\(IN\), TLS alert, unknown \(628\)', row['stderr'], re.I) and
                re.search(r'SSL routines::[^\r\n]*alert certificate required', row['stderr'], re.I))
    outgoing_failure = re.search(r'\(OUT\), TLS alert, (?!close notify\b)', row['stderr'], re.I)
    return (row['exit_code'] in (35, 56, 60, 98) and row['code'] == 0 and
            not outgoing_failure and bool(named or required))


def openssl_rejection(row):
    return (row['exit_code'] == 1 and row['code'] == 0 and 'verify return:1' in row['stderr'] and
            bool(re.search(r'alert.*(?:certificate|unknown ca|handshake failure|access denied)',
                           row['stderr'], re.IGNORECASE)))


class Lab(ingress.Runner):
    def __init__(self, report):
        super().__init__(report)
        self.client = self.network = None

    def client_exec(self, *args, data=None, ok=True, timeout=15, discard=False):
        # Do not inherit proxy, .curlrc, CA overrides or TLS key logging.
        env = ['LC_ALL=C', 'SSLKEYLOGFILE=', 'CURL_HOME=/nonexistent',
               'CURL_CA_BUNDLE=', 'SSL_CERT_FILE=', 'SSL_CERT_DIR=', 'HTTP_PROXY=',
               'HTTPS_PROXY=', 'ALL_PROXY=', 'NO_PROXY=*']
        command = ['podman', 'exec', '-i', '--user', USER]
        for item in env:
            command += ['--env', item]
        result = bounded_client(command+[self.client, '/usr/bin/setsid', '--wait', *args],
                                data=data, timeout=timeout, discard=discard)
        diagnostics(result.stderr)
        require(not ok or result.returncode == 0, 'client command failed')
        return result

    def write(self, path, data, client=False):
        script = 'umask 077; cat >'+shlex.quote(path)
        if client:
            return self.client_exec('/bin/sh', '-eu', '-c', script, data=data)
        return self.command(['podman', 'exec', '-i', '--user', USER, self.container,
                             '/bin/sh', '-eu', '-c', script], data=data)

    def create(self, runtime, client):
        network = 'file-mover-tls-'+uuid.uuid4().hex
        self.command(['podman', 'network', 'create', '--internal', '--disable-dns', network])
        self.network = network  # Only a successfully created network is ours to remove.
        for role, image in [('server', runtime), ('client', client)]:
            result = self.command(['podman', 'create', '--pull=never', '--network', self.network,
                '--user', USER, '--cap-drop=ALL', '--security-opt=no-new-privileges',
                '--env', 'LC_ALL=C', '--entrypoint', '/bin/sh', image, '-c', 'exec sleep infinity'])
            container = result.stdout.decode().strip()
            if role == 'server':
                self.container = container
            else:
                self.client = container
            self.command(['podman', 'start', container])
        self.report['network'] = json.loads(self.command(['podman', 'network', 'inspect', self.network]).stdout)[0]
        require(self.report['network']['internal'] is True, 'network is not internal')
        self.report['containers'] = {}
        for role, name in [('server', self.container), ('client', self.client)]:
            info = json.loads(self.command(['podman', 'inspect', name]).stdout)[0]
            require(not info['HostConfig'].get('PortBindings'), 'fixture published a host port')
            self.report['containers'][role] = dict(id=name, image=info['Image'],
                ports=info['HostConfig'].get('PortBindings'), network=self.network)
        info = json.loads(self.command(['podman', 'inspect', self.container]).stdout)[0]
        self.ip = info['NetworkSettings']['Networks'][self.network]['IPAddress']
        require(self.ip, 'server has no private network address')

    def copy(self, container, data):
        # Seekable stdin plus exact tar end blocks avoids Podman's pipe/trailer bug.
        with tempfile.TemporaryFile() as file:
            file.write(data)
            file.seek(0)
            result = subprocess.run(['podman', 'cp', '--archive=false', '-', container+':/tmp'],
                                    stdin=file, capture_output=True, timeout=60)
            require(result.returncode == 0, 'fixture archive copy failed')

    def close(self):
        errors = []
        if self.client:
            try:
                result = self.command(['podman', 'rm', '-f', self.client], ok=False)
                self.report['client_cleanup_exit_code'] = result.returncode
                if result.returncode:
                    errors.append('client cleanup failed')
            except Exception as error:
                errors.append('client cleanup: '+type(error).__name__)
        try:
            if self.container:
                result = self.command(['podman', 'rm', '-f', self.container], ok=False)
                self.report['cleanup'] = dict(exit_code=result.returncode,
                    stdout=result.stdout.decode(errors='replace'), stderr=result.stderr.decode(errors='replace'))
                if result.returncode:
                    errors.append('server cleanup failed')
        except Exception as error:
            errors.append('server cleanup: '+type(error).__name__)
        for process in self.processes:
            try:
                if process.poll() is None:
                    process.terminate()  # Only the CLI child we created, by PID.
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate(timeout=5)
            except Exception as error:
                errors.append('process cleanup: '+type(error).__name__)
        if self.network:
            try:
                result = self.command(['podman', 'network', 'rm', self.network], ok=False)
                self.report['network_cleanup_exit_code'] = result.returncode
                if result.returncode:
                    errors.append('network cleanup failed')
            except Exception as error:
                errors.append('network cleanup: '+type(error).__name__)
        require(not errors, '; '.join(errors))


def check_identity(text):
    fields = dict(line.split(':', 1) for line in text.splitlines() if ':' in line)
    require(fields['Uid'].split() == ['1000']*4 and fields['Gid'].split() == ['1001']*4, 'wrong fixture identity')
    require(all(int(fields[k], 16) == 0 for k in ('CapInh', 'CapPrm', 'CapEff', 'CapBnd')), 'fixture has capabilities')
    require(fields['NoNewPrivs'].strip() == '1', 'fixture can gain privileges')


def run_profile(lab, profile, config, der, artifact):
    base = '/tmp/tls-interop/'+profile
    binary, config_path = base+'/file-mover', base+'/config.json'
    credentials = base+'/credentials'
    result = dict(profile=profile, binary_sha256=artifact['sha256'], config=config,
                  clients=[], controls=[], preservation=[], passed=False)
    lab.report['profiles'].append(result)
    require(lab.execute('sha256sum', binary).stdout.decode().split()[0] == artifact['sha256'], 'server binary changed in copy')
    require(lab.execute('getconf', 'GNU_LIBC_VERSION').stdout.strip() == b'glibc 2.22', 'not SLES glibc2.22')
    result['ldd'] = lab.execute('ldd', '-r', binary).stdout.decode()
    require('not found' not in result['ldd'] and 'undefined symbol' not in result['ldd'], 'server relocation failed')
    require(b'build=production' in lab.execute(binary, '--check-platform').stdout, 'server is not production build')
    for name in tls_proof_fixture.CERTIFICATES:
        if name not in ('ca', 'other-ca') and 'client' not in name:
            continue
        for key in (False, True) if 'client' in name else (False,):
            source = credentials+'/'+name+('.key.der' if key else '.der')
            destination = credentials+'/'+name+('.key.pem' if key else '.pem')
            tool = 'pkey' if key else 'x509'
            lab.client_exec('/bin/sh', '-eu', '-c', 'umask 077; /usr/bin/openssl '+tool+
                ' -inform DER -in '+shlex.quote(source)+' -out '+shlex.quote(destination))
            require(lab.client_exec('stat', '-c', '%u:%g:%a', destination).stdout.strip() == b'1000:1001:600', 'PEM custody differs')

    def control(action, path=config_path, success=True):
        before = time.monotonic()
        value = lab.execute(binary, action, path, ok=False, timeout=12)
        row = dict(action=action, exit_code=value.returncode, seconds=round(time.monotonic()-before, 4))
        # Control output contains public policy/process identity only.
        row['stdout'], row['stderr'] = value.stdout.decode(), value.stderr.decode()
        result['controls'].append(row)
        require((value.returncode == 0) == success, 'unexpected control outcome: '+action)
        return json.loads(value.stdout) if success else None

    def operator(path):
        row = lab.http(config['native_ingress']['operator_socket'], ingress.wire('GET', path), USER)
        require(row.get('code') == 200, 'private operator read failed')
        return row['body']

    def start():
        lab.shell(': >'+shlex.quote(base+'/state/service.log'))
        process = lab.spawn('/bin/sh', '-eu', '-c', 'exec '+shlex.quote(binary)+' '+shlex.quote(config_path)+
                            ' >'+shlex.quote(base+'/state/service.log')+' 2>&1')
        def ready():
            require(process.poll() is None, 'server exited before readiness')
            return b'Ready on native producer' in lab.execute('cat', base+'/state/service.log').stdout
        ingress.wait_until(ready, 'native server readiness missing', seconds=15)
        require(operator('/healthz')['state'] == 'Running', 'private health is not running')
        return process

    def stop(process):
        require(control('--stop')['phase'] == 'Stopped', 'shutdown did not finish')
        process.communicate(timeout=10)
        require(process.returncode == 0, 'server exit was not clean')

    server_sha = sha(der['server.der'])

    def curl(label, body=None, certificate='client', tls='1.3', method='POST', path='/api/v2/jobs', host='localhost', ca='ca', headers=(), verbose=False):
        body_path = None
        if body is not None:
            body_path = base+'/request.json'
            lab.write(body_path, json.dumps(body, ensure_ascii=False).encode(), client=True)
        args = curl_args(lab.ip, PORT, credentials, certificate, tls, method, path, body_path, host, ca, headers)
        if verbose:
            # Disposable negative cases only: curl's public record/alert
            # diagnostics identify peer direction; key/session logs stay off.
            args += ['--verbose']
        before = time.monotonic()
        value = lab.client_exec(*args, ok=False)
        require(len(value.stdout) <= 131072 and len(value.stderr) <= 16384, 'oversized client capture')
        row = dict(label=label, client='curl', tls=tls, certificate=certificate, method=method, path=path,
                   host=host, ca=ca, request=body, exit_code=value.returncode,
                   stderr=diagnostics(value.stderr), seconds=round(time.monotonic()-before, 4))
        row['stdout_bytes'] = len(value.stdout)
        result['clients'].append(row)
        row.update(parse_curl(value.stdout))
        if row['code']:
            require(row['exit_code'] == 0 and row['verify_result'] == 0 and row['remote_ip'] == lab.ip, 'curl HTTPS evidence incomplete')
            require(row['server_sha256'] == server_sha, 'curl observed wrong server leaf')
        return row

    def openssl(label, body, tls, certificate='client', ca='ca', host='localhost', discard=False):
        raw = ingress.wire(body=body).replace(b'Host: localhost\r\n', f'Host: localhost:{PORT}\r\n'.encode())
        args = openssl_args(lab.ip, PORT, credentials, certificate, tls, host, ca)
        before = time.monotonic()
        # OpenSSL authenticates/reads TLS internally. For receipt loss its HTTP
        # stdout goes to DEVNULL, never to the submitting application. This is
        # not a deterministic network fault or pre-admission disconnect.
        value = lab.client_exec(*args, data=raw, ok=False, discard=discard)
        stdout, stderr = value.stdout, value.stderr
        require(len(stdout) <= 131072 and len(stderr) <= 16384, 'oversized OpenSSL capture')
        text = diagnostics(stderr)
        row = dict(label=label, client='openssl', tls=tls, certificate=certificate, host=host, ca=ca, code=0,
                   request=body, exit_code=value.returncode, stderr=text, discarded_http_receipt=discard,
                   seconds=round(time.monotonic()-before, 4))
        if value.returncode == 0:
            require('verify return:1' in text and 'verify error' not in text.lower(), 'OpenSSL did not establish verification')
            if not discard:
                row.update(parse_http(stdout))
        else:
            require(not stdout.startswith(b'HTTP/'), 'TLS refusal exposed HTTP')
        result['clients'].append(row)
        return row

    lab.execute(binary, '--initialize-source', config_path)
    enrollment = lab.execute('cat', base+'/source/.file-mover/source-enrollment.json').stdout
    process = start()
    for side in ('server', 'client'):
        text = (lab.execute('cat', '/proc/self/status') if side == 'server' else lab.client_exec('cat', '/proc/self/status')).stdout.decode()
        check_identity(text)
        result[side+'_identity'] = text

    request = producer_request(base+'/source/current', {name: len(data) for name, data in PAYLOADS.items()})
    result['submission'] = request
    # Before any valid submission, every denial must leave the job ledger empty.
    for tls in ('1.2', '1.3'):
        for name in (None, 'untrusted-client', 'expired-client', 'wrong-usage-client'):
            row = curl('invalid-client', request, certificate=name, tls=tls, verbose=True)
            require(tls_rejection(row), 'invalid client did not receive an explicit certificate TLS alert')
            row = openssl('invalid-client', request, tls, certificate=name)
            require(openssl_rejection(row), 'OpenSSL invalid client did not establish verified-server certificate alert')
        row = curl('unapproved-same-ca', request, certificate='unapproved-client', tls=tls)
        require(row['code'] == 403 and row['json']['error'] == 'caller_not_authorized', 'unapproved same-CA client was not denied after TLS')
        row = openssl('unapproved-same-ca', request, tls, certificate='unapproved-client')
        require(row['exit_code'] == 0 and row['code'] == 403 and row['json']['error'] == 'caller_not_authorized',
                'OpenSSL unapproved same-CA client was not denied after TLS')
        for host, ca in [('wrong.invalid', 'ca'), ('localhost', 'other-ca')]:
            row = curl('server-verification-refused', request, tls=tls, host=host, ca=ca)
            require(row['exit_code'] == 60 and row['code'] == 0, 'server verification refusal was not a certificate failure')
            if ca == 'other-ca':
                require(row['verify_result'] != 0, 'wrong trust root did not fail chain validation')
            else:
                require(re.search(r'no alternative certificate|subject name|hostname', row['stderr'], re.I),
                        'wrong hostname did not fail name validation')
            row = openssl('server-verification-refused', request, tls, host=host, ca=ca)
            require(row['exit_code'] != 0 and 'verify error' in row['stderr'].lower(), 'OpenSSL did not refuse bad server verification')
    require(operator('/api/v2/retention')['details']['retained_jobs'] == 0, 'certificate refusal admitted a job')

    lost = openssl('discarded-receipt', request, '1.2', discard=True)
    require(lost['exit_code'] == 0, 'receipt-discard client failed TLS')
    ingress.wait_until(lambda: operator('/api/v2/jobs/1').get('source_paths_released') is True,
                       'discarded receipt did not establish durable handoff', seconds=20)
    accepted = curl('receipt-recovery', request, tls='1.2')
    require(accepted['code'] == 202, 'curl receipt recovery was not accepted')
    validate_producer_response(202, accepted['json'], request)
    receipt, job = accepted['json'], accepted['json']['job_id']
    result['receipt'] = receipt
    ingress.wait_until(lambda: operator('/api/v2/jobs/'+job).get('state') == 'Committed', 'recording never committed', seconds=20)
    area = base+'/destination/'+request['recording_id']
    manifest_bytes = lab.execute('cat', area+'/COMMITTED.json').stdout
    manifest = validate_writer_bytes(manifest_bytes, request)
    require(manifest['job_id'] == job, 'manifest job differs from receipt')
    for item in manifest['files']:
        payload = PAYLOADS[item['path']]
        require(item['size_bytes'] == str(len(payload)) and item['sha256'] == sha(payload), 'manifest measures wrong content')
    result['manifest_sha256'] = sha(manifest_bytes)
    owned_paths = [area+'/COMMITTED.json', base+'/source/.file-mover/source-enrollment.json']
    for index, (name, data) in enumerate(PAYLOADS.items()):
        require(lab.execute('cat', area+'/'+name).stdout == data, 'initial destination differs from known input')
        claim = base+'/source/.file-mover/'+job+'-'+str(index)+'/data'
        require(lab.execute('cat', claim).stdout == data, 'initial private claim differs from known input')
        owned_paths += [area+'/'+name, claim]
    for name, data in REUSED.items():
        lab.write(base+'/source/current/'+name, data)
        owned_paths.append(base+'/source/current/'+name)
    identities = {path: lab.execute('stat', '-c', '%d:%i:%s:%F', path).stdout.decode().strip()
                  for path in owned_paths}
    result['original_file_identities'] = identities

    def preserved(stage):
        for index, (name, data) in enumerate(PAYLOADS.items()):
            require(lab.execute('cat', area+'/'+name).stdout == data, 'destination payload changed: '+stage)
            require(lab.execute('cat', base+'/source/.file-mover/'+job+'-'+str(index)+'/data').stdout == data, 'private claim changed: '+stage)
            require(lab.execute('cat', base+'/source/current/'+name).stdout == REUSED[name], 'replay touched producer-reused leaf: '+stage)
        require(lab.execute('cat', area+'/COMMITTED.json').stdout == manifest_bytes, 'immutable manifest changed: '+stage)
        require(lab.execute('cat', base+'/source/.file-mover/source-enrollment.json').stdout == enrollment, 'enrollment changed: '+stage)
        for path, identity in identities.items():
            require(lab.execute('stat', '-c', '%d:%i:%s:%F', path).stdout.decode().strip() == identity,
                    'original inode/size changed: '+stage)
        require(operator('/api/v2/retention')['details']['retained_jobs'] == 1, 'unexpected job allocation: '+stage)
        result['preservation'].append(dict(stage=stage, manifest_sha256=sha(manifest_bytes),
            destination_sha256={name: sha(data) for name, data in PAYLOADS.items()},
            reused_source_sha256={name: sha(data) for name, data in REUSED.items()}, private_claims_preserved=True))

    def replay(stage, certificate='client'):
        reordered = copy.deepcopy(request)
        reordered['files'].reverse()
        for tls, body in [('1.2', request), ('1.3', reordered)]:
            row = curl(stage, body, certificate=certificate, tls=tls)
            require(row['code'] == 202 and row['json'] == receipt, 'curl replay changed original receipt')
            row = openssl(stage, body, tls, certificate=certificate)
            require(row['exit_code'] == 0 and row['code'] == 202 and row['json'] == receipt, 'OpenSSL replay changed original receipt')
        preserved(stage)

    replay('path-reuse-reordered')
    for method, path, body, headers, expected, error in [
        ('POST', '/api/v2/jobs', dict(request, generator_id='spoofed'), (), 403, 'unknown_generator'),
        ('POST', '/api/v2/jobs', dict(request, source_directory=base+'/source/.file-mover'), (), 403, 'source_outside_scope'),
        ('POST', '/api/v2/jobs', request, ('X-File-Mover-Generator: fixture',), 400, 'unsupported_headers'),
        ('GET', '/healthz', None, (), 403, 'producer_route_forbidden'),
        ('GET', '/api/v2/retention', None, (), 403, 'producer_route_forbidden'),
        ('GET', '/api/v2/jobs/'+job, None, (), 403, 'producer_route_forbidden'),
        ('GET', '/api/v2/jobs', None, (), 405, 'method_not_allowed')]:
        row = curl('native-boundary-refusal', body, method=method, path=path, headers=headers)
        require(row['code'] == expected and row['json']['error'] == error, 'native boundary refusal changed')
    preserved('after-boundary-refusals')
    before = control('--tls-status')
    stop(process)
    process = start()
    restarted = control('--tls-status')
    require(restarted['instance_id'] != before['instance_id'], 'restart did not change PID:start')
    replay('original-state-restart')

    replacement = copy.deepcopy(config)
    replacement['native_ingress'].update(server_certificates=[credentials+'/replacement-server.der'],
        server_key=credentials+'/replacement-server.key.der',
        clients=[dict(sha256=sha(der['unapproved-client.der']), generator_id='fixture')])
    lab.write(config_path, json.dumps(replacement).encode())
    result['replacement_policies'] = [copy.deepcopy(replacement)]
    current = control('--tls-status')
    activated = control('--reload-tls')
    require(activated['instance_id'] == current['instance_id'] and
            activated['status']['generation'] == current['status']['generation']+1 and
            activated['status']['policy_sha256'] != current['status']['policy_sha256'] and
            activated['status']['server_sha256'] == sha(der['replacement-server.der']) and
            not activated['status']['draining'] and not activated['busy'], 'replacement activation evidence incomplete')
    server_sha = sha(der['replacement-server.der'])
    for tls in ('1.2', '1.3'):
        row = curl('revoked-old-client', request, tls=tls)
        require(row['code'] == 403 and row['json']['error'] == 'caller_not_authorized', 'old client retained authorization')
        row = openssl('revoked-old-client', request, tls)
        require(row['exit_code'] == 0 and row['code'] == 403 and row['json']['error'] == 'caller_not_authorized', 'OpenSSL old client retained authorization')
    replay('replacement-client-and-server', certificate='unapproved-client')
    # Remove the original client CA as well as its approved leaf. Server trust
    # stays under the original CA; this is client-CA rotation, not server-CA rollover.
    replacement['native_ingress'].update(client_ca_certificates=[credentials+'/other-ca.der'],
        clients=[dict(sha256=sha(der['untrusted-client.der']), generator_id='fixture')])
    lab.write(config_path, json.dumps(replacement).encode())
    result['replacement_policies'].append(copy.deepcopy(replacement))
    current = activated
    activated = control('--reload-tls')
    require(activated['instance_id'] == current['instance_id'] and
            activated['status']['generation'] == current['status']['generation']+1 and
            activated['status']['policy_sha256'] != current['status']['policy_sha256'] and
            activated['status']['server_sha256'] == current['status']['server_sha256'] and
            not activated['status']['draining'] and not activated['busy'], 'client CA rotation incomplete')
    for tls in ('1.2', '1.3'):
        row = curl('removed-client-ca', request, certificate='unapproved-client', tls=tls, verbose=True)
        require(tls_rejection(row), 'removed client CA retained TLS access')
        row = openssl('removed-client-ca', request, tls, certificate='unapproved-client')
        require(openssl_rejection(row), 'OpenSSL removed client CA retained TLS access')
    replay('replacement-client-ca', certificate='untrusted-client')
    invalid = copy.deepcopy(replacement)
    invalid['native_ingress']['server_key'] = credentials+'/invalid.key.der'
    lab.write(base+'/invalid.json', json.dumps(invalid).encode())
    control('--reload-tls', path=base+'/invalid.json', success=False)
    unchanged = control('--tls-status')
    for key in ('generation', 'policy_sha256', 'server_sha256', 'client_sha256'):
        require(unchanged['status'][key] == activated['status'][key], 'invalid reload changed active policy')
    require(unchanged['instance_id'] == activated['instance_id'], 'invalid reload replaced process')
    replay('invalid-policy-preserved', certificate='untrusted-client')
    stop(process)
    process = start()
    after_restart = control('--tls-status')
    require(after_restart['instance_id'] != activated['instance_id'] and
            after_restart['status']['policy_sha256'] == activated['status']['policy_sha256'],
            'replacement policy did not survive configured restart')
    row = curl('revoked-after-restart', request, verbose=True)
    require(tls_rejection(row), 'restart revived removed client CA')
    replay('replacement-policy-restart', certificate='untrusted-client')
    stop(process)
    result['passed'] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production-gate', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True, help='new report path; never overwritten')
    args = parser.parse_args()
    # Exclusive report reservation precedes every container/network side effect.
    with args.report.open('x', encoding='utf-8') as output:
        report = dict(status='FAILED', profiles=[], requests=[], limits=[
            'Finite modern curl/OpenSSL clients against production SLES debug/release binaries; no runtime source change.',
            'Receipt discard is application receipt loss, not a deterministic pre-admission disconnect or network outage.',
            'Client timing includes OCI exec overhead; no throughput, realtime or OS-quota claim. Server certificate changes remain under the original server CA.',
            'Future-valid client leaf, other TLS backends/legacy clients, bundle/systemd/NFS/FIPS/shipping and all eight FR gates remain open.'])
        lab = Lab(report)
        try:
            platform, artifacts, report['gate'] = ingress.load_gate(args.production_gate)
            saved = json.loads((args.production_gate/'report.json').read_bytes())
            require(saved['test_scope'] == 'full', 'retained gate is scoped')
            for field, name in [('builder_recipe_sha256', 'Containerfile.rust'),
                                ('dependency_pins_sha256', 'rust-qualified-dependencies.json'),
                                ('tls_fixture_helper_sha256', 'tls_proof_fixture.py')]:
                require(saved[field] == sha((ROOT/'scripts'/name).read_bytes()), 'gate build input changed: '+name)
            pins = json.loads((ROOT/'scripts/tls-client-platform.json').read_bytes())
            require('@sha256:' in pins['client_image'], 'client image is not pinned')
            report['client_platform'] = pins
            image = json.loads(lab.command(['podman', 'image', 'inspect', pins['client_image']]).stdout)[0]
            require(image['Architecture'] == 'amd64' and image['Os'] == 'linux', 'wrong client architecture')
            report['client_image'] = dict(id=image['Id'], digest=image.get('Digest'), architecture=image['Architecture'])
            lab.create(platform['runtime'], pins['client_image'])
            for role, image_name in [('server', platform['runtime']), ('client', pins['client_image'])]:
                require('@sha256:' in image_name, 'fixture image is not digest-pinned')
            report['client_tools'] = dict(curl=lab.client_exec(pins['curl'], '--version').stdout.decode(),
                openssl=lab.client_exec(pins['openssl'], 'version').stdout.decode(),
                executable_hashes=lab.client_exec('sha256sum', pins['curl'], pins['openssl']).stdout.decode())
            executable_hashes = {line.split()[1]: line.split()[0]
                                 for line in report['client_tools']['executable_hashes'].splitlines()}
            require(executable_hashes == pins['executables_sha256'], 'client executable hashes differ from pins')
            require(report['client_tools']['curl'].startswith('curl '+pins['curl_version']+' ') and
                    'OpenSSL/'+pins['openssl_version'] in report['client_tools']['curl'] and
                    report['client_tools']['openssl'].startswith('OpenSSL '+pins['openssl_version']+' '), 'client version/backend differs from pins')
            with tempfile.TemporaryDirectory(prefix='file-mover-client-fixture-') as temporary:
                temporary = Path(temporary)
                report['fixture'] = tls_proof_fixture.generate(temporary/'der', temporary/'private.tar')
                der = {name: (temporary/'der'/name).read_bytes() for name in tls_proof_fixture.FILES}
                server, client, configs = fixtures(artifacts, der)
                report['fixture_archives_sha256'] = dict(server=sha(server), client=sha(client))
                lab.copy(lab.container, server)
                lab.copy(lab.client, client)
                for profile in ('debug', 'release'):
                    print('Independent TLS clients: '+profile, flush=True)
                    run_profile(lab, profile, configs[profile], der, report['gate']['artifacts'][profile])
            report['driver_sha256'] = {name: sha((ROOT/'scripts'/name).read_bytes()) for name in
                ('check-tls-clients.py', 'tls_client_tools.py', 'tls-client-platform.json', 'check-producer-ingress.py',
                 'check-rust-sles.py', 'nfs_fixture_contract.py', 'tls_proof_fixture.py', 'rust-platform.json')}
            report['git_commit'] = lab.command(['git', 'rev-parse', 'HEAD']).stdout.decode().strip()
            report['status'] = 'PASSED'
        except Exception:
            report['error'] = traceback.format_exc()
            if lab.container:
                report['failure_service_logs'] = {}
                for profile in ('debug', 'release'):
                    try:
                        value = lab.execute('tail', '-c', '8192',
                            '/tmp/tls-interop/'+profile+'/state/service.log', ok=False, timeout=3)
                        if value.returncode == 0:
                            report['failure_service_logs'][profile] = diagnostics(value.stdout)
                    except Exception:
                        report['failure_service_logs'][profile] = 'log unavailable'
        finally:
            try:
                lab.close()
            except Exception as error:
                report['status'] = 'FAILED'
                report['cleanup_error'] = str(error)
            output.write(json.dumps(report, indent=2)+'\n')
        print(report['status']+': independent curl/OpenSSL client qualification', flush=True)
        return 0 if report['status'] == 'PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
