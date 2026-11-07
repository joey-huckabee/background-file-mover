#!/usr/bin/env python3
"""Prove reply-loss fixture capability without executing any Rust binary."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
import uuid
from nfs_endpoints import Endpoints
from nfs_reply_relay import ReplyRelay, preflight


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--operation', choices=('remove', 'link', 'both'), default='remove')
    parser.add_argument('--role', choices=('source', 'destination'), default='destination')
    parser.add_argument('--backend-restart', action='store_true', help='After source controls, prove real backend stop/restart transport recovery')
    parser.add_argument('--synchronization', action='store_true', help='Observe native sync calls and prove available reply-withholding boundaries')
    args = parser.parse_args()
    assert not args.backend_restart or args.role == 'source', 'backend restart requires source role'
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / 'scripts/rust-platform.json').read_text(encoding='utf-8'))
    label = 'reply-capability-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    output = root / 'rust/validation' / label
    output.mkdir()
    engine = ['podman', '--connection', 'podman-machine-default-root']
    containers, volumes, mounts, servers, tasks = [], [], [], [], []
    client = relay = None
    network = 'bfm-' + label.lower()
    report = dict(status='FAILED', run_id=label, operation=args.operation, role=args.role, rust_executed=False, cleanup_errors=[],
                  config=config, driver_sha256={n: hashlib.sha256((root / 'scripts' / n).read_bytes()).hexdigest()
                      for n in ('check-nfs-reply-capability.py', 'nfs_reply_relay.py', 'nfs_rpc.py',
                                'nfs_reply_proxy.py', 'nfs_endpoints.py', 'test_nfs_rpc.py', 'nfs_relay_restart.py', *(['nfs_sync_capability.py', 'nfs_sync_support.py', 'nfs_syscall_trace.py', 'nfs_sync_probe.c'] if args.synchronization else []))})

    def run(args, check=True):
        value = subprocess.run(engine + args, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=45)
        if check and value.returncode:
            raise RuntimeError(str(args) + ': ' + value.stdout + value.stderr)
        return value

    def execute(script, user=None, check=True):
        return run(['exec', *(['--user', user] if user else []), client, '/bin/sh', '-eu', '-c', script], check)

    def spawn(script, name):
        log = (output / (name + '.log')).open('w', encoding='utf-8')
        process = subprocess.Popen(engine + ['exec', '--user', '1000:1000', client,
                                              '/bin/sh', '-eu', '-c', script], stdout=log, stderr=log)
        tasks.append((process, log))
        return process

    try:
        tests = subprocess.run([sys.executable, str(root / 'scripts/test_nfs_rpc.py'), '-v'],
                               capture_output=True, text=True, timeout=20)
        report['decoder_tests'] = dict(passed=tests.returncode == 0, output=tests.stdout + tests.stderr)
        assert tests.returncode == 0
        image = 'localhost/background-file-mover-e2-nfs'
        report['server_image'] = run(['image', 'inspect', image, '--format', '{{.Id}}']).stdout.strip()
        run(['network', 'create', '--internal', network])
        volume = network + '-source'
        run(['volume', 'create', volume])
        volumes.append(volume)
        server = run(['create', '--privileged', '--network', network, '--volume', volume + ':/exports', image]).stdout.strip()
        containers.append(server)
        servers.append(server)
        run(['start', server])
        for _ in range(40):
            if 'NFS_READY' in run(['logs', server]).stdout:
                break
            time.sleep(.5)
        else:
            raise RuntimeError('source server not ready')
        address = json.loads(run(['inspect', server]).stdout)[0]['NetworkSettings']['Networks'][network]['IPAddress']
        client = run(['create', '--network', network, '--cap-drop', 'all', '--cap-add', 'SYS_ADMIN',
                      *(['--cap-add','SYS_PTRACE','--cap-add','DAC_READ_SEARCH'] if args.synchronization else []),
                      '--security-opt', 'no-new-privileges', '--entrypoint', '/bin/sh', config['runtime'],
                      '-c', 'exec sleep infinity']).stdout.strip()
        containers.append(client)
        run(['start', client])
        report['kernel'] = execute('uname -r').stdout.strip()
        assert execute('getconf GNU_LIBC_VERSION').stdout.strip() == 'glibc 2.22'

        def make_relay(backend):
            nonlocal relay
            relay = ReplyRelay(run, network, config['builder'], backend, containers, output)
            return relay

        report['endpoints'] = dict(passed=False)
        endpoints = Endpoints(run, execute, server, client, address,
                              f'addr={address},vers=4.1,proto=tcp,port=2049,hard,timeo=10,retrans=1,noac',
                              network, image, containers, volumes, servers, mounts, report['endpoints'],
                              destination_relay=make_relay if args.role == 'destination' else None,
                              source_relay=make_relay if args.role == 'source' else None)
        report['relay_security'] = run(['exec', relay.container, 'cat', '/proc/1/status']).stdout
        operations = (11, 28) if args.operation == 'both' else (11 if args.operation == 'link' else 28,)
        assert args.operation != 'both' or args.role == 'source', 'combined controls require distinct source probe paths'
        report['preflights'] = {}
        for operation in operations:
            proof = dict(passed=False, cases=[])
            report['preflights'][str(operation)] = proof
            if len(operations) == 1:
                report['preflight'] = proof
            preflight(relay, endpoints, run, execute, spawn, output, proof, operation, args.role)
            assert proof['passed']
        if args.backend_restart:
            from nfs_relay_restart import qualify
            report['backend_restart'] = dict(passed=False)
            qualify(relay, endpoints, run, execute, spawn, output, report['backend_restart'])
            assert report['backend_restart']['passed']
        if args.synchronization:
            assert args.role=='destination', 'sync capability uses destination relay'
            from nfs_sync_capability import qualify
            report['synchronization'] = dict(passed=False)
            qualify(relay,endpoints,run,execute,spawn,output,client,containers,config,report['synchronization'])
            assert report['synchronization']['passed']
        report['status'] = 'PASSED'
    except Exception as error:
        report.update(error=f'{type(error).__name__}: {error}', traceback=traceback.format_exc())
    finally:
        if relay:
            try:
                relay.release()
                report['relay_final'] = relay.state(strict=False)
                report['relay_log'] = run(['logs', relay.container], check=False).stdout
            except Exception as error:
                report['cleanup_errors'].append(str(error))
        for process, log in tasks:
            try:
                process.wait(timeout=30)
            except Exception as error:
                report['cleanup_errors'].append(str(error))
            log.close()
        for target, path in reversed(mounts):
            try:
                run(['exec', target, 'umount', path])
            except Exception as error:
                report['cleanup_errors'].append(str(error))
        if not report['cleanup_errors']:
            for server in servers:
                run(['exec', server, 'rpc.nfsd', '0'], check=False)
                run(['exec', server, 'exportfs', '-au'], check=False)
            for target in reversed(containers):
                if run(['rm', '--force', target], check=False).returncode:
                    report['cleanup_errors'].append('container removal failed: ' + target)
            for volume in volumes:
                if run(['volume', 'rm', volume], check=False).returncode:
                    report['cleanup_errors'].append('volume removal failed: ' + volume)
            if run(['network', 'rm', network], check=False).returncode:
                report['cleanup_errors'].append('network removal failed: ' + network)
        if report['cleanup_errors']:
            report['status'] = 'FAILED'
            report['recovery_resources'] = dict(containers=containers, volumes=volumes, network=network, mounts=mounts)
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(report['status'] + ': ' + str(output), flush=True)
        if 'error' in report:
            print(report['error'], flush=True)
    return 0 if report['status'] == 'PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
