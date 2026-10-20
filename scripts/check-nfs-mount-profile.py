#!/usr/bin/env python3
"""Qualify NFS mount observations and optional supervised workers in owned SLES containers."""
from datetime import datetime, timezone
import base64
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import time
import traceback
import uuid

from nfs_mount_profile import Refused, parse, validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production-gate', type=Path)
    parser.add_argument('--qualification-gate', type=Path)
    parser.add_argument('--same-share', action='store_true', help='Run buffered same-share service and crash recovery cases instead of authorization cases')
    parser.add_argument('--buffered-reads', action='store_true', help='Qualify blocked copy/verification reads and coordinator-death recovery on same/separate shares')
    parser.add_argument('--buffered-publication', action='store_true', help='Qualify returned-LINK/pre-sync and blocked-unlink file/manifest recovery on buffered same/separate shares')
    parser.add_argument('--buffered-post-unlink', action='store_true', help='Qualify file/manifest crashes after staging unlink returned, before directory sync, on buffered same/separate shares')
    parser.add_argument('--buffered-claims', action='store_true', help='Qualify blocked custody LINK and producer-name REMOVE before HTTP 202 on buffered same/separate shares')
    parser.add_argument('--buffered-bootstrap', action='store_true', help='Qualify interrupted enrolled-empty/populated startup on buffered same/separate shares')
    parser.add_argument('--buffered-sync', action='store_true', help='Trace eight buffered claim/delivery workers and prove available native sync reply-withholding controls')
    parser.add_argument('--buffered-io', action='store_true', help='Trace eight buffered workers with descriptor/payload/filehandle I/O attribution')
    parser.add_argument('--buffered-commit', action='store_true', help='Prove payload fchmod COMMIT withholding before eight release/death recovery cases')
    parser.add_argument('--buffered-unstable', action='store_true', help='Prove UNSTABLE WRITE success withheld before eight buffered recovery cases')
    parser.add_argument('--live-loss', action='store_true', help='Keep the coordinator alive during buffered COMMIT or UNSTABLE reply drop')
    parser.add_argument('--manifest-capability', action='store_true', help='Trace four actual manifest workers, then prove four successful-reply hold/release controls')
    parser.add_argument('--manifest-loss', action='store_true', help='Repeat manifest controls, then live and coordinator-death WRITE reply-loss recovery')
    parser.add_argument('--claim-capability', action='store_true', help='Prove eight buffered actual-claim LINK/REMOVE successful-reply hold/release controls')
    parser.add_argument('--claim-loss', action='store_true', help='Repeat eight buffered claim controls, then sixteen live/death LINK/REMOVE reply-loss recoveries')
    args = parser.parse_args()
    assert not args.claim_loss or args.production_gate, 'claim-loss requires both gates'
    assert not args.claim_capability or args.production_gate, 'claim-capability requires both gates'
    assert not args.manifest_loss or args.production_gate, 'manifest-loss requires both gates'
    assert not args.manifest_capability or args.production_gate, 'manifest-capability requires both gates'
    assert not args.live_loss or (args.buffered_commit or args.buffered_unstable), 'live-loss requires a payload reply matrix'
    assert bool(args.production_gate) == bool(args.qualification_gate), 'both gates required'
    assert not args.same_share or args.production_gate, 'same-share requires both gates'
    assert not args.buffered_reads or args.production_gate, 'buffered-reads requires both gates'
    assert not args.buffered_publication or args.production_gate, 'buffered-publication requires both gates'
    assert not args.buffered_post_unlink or args.production_gate, 'buffered-post-unlink requires both gates'
    assert not args.buffered_claims or args.production_gate, 'buffered-claims requires both gates'
    assert not args.buffered_bootstrap or args.production_gate, 'buffered-bootstrap requires both gates'
    assert not args.buffered_sync or args.production_gate, 'buffered-sync requires both gates'
    assert not args.buffered_io or args.production_gate, 'buffered-io requires both gates'
    assert not args.buffered_commit or args.production_gate, 'buffered-commit requires both gates'
    assert not args.buffered_unstable or args.production_gate, 'buffered-unstable requires both gates'
    assert sum((args.same_share, args.buffered_reads, args.buffered_publication, args.buffered_post_unlink, args.buffered_claims, args.buffered_bootstrap, args.buffered_sync, args.buffered_io, args.buffered_commit, args.buffered_unstable, args.manifest_capability, args.manifest_loss, args.claim_capability, args.claim_loss)) <= 1, 'select one worker matrix'
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / 'scripts/rust-platform.json').read_text(encoding='utf-8'))
    label = 'mount-profile-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    output = root / 'rust/validation' / label
    output.mkdir(parents=True)
    print('Mount-profile validation: ' + str(output), flush=True)
    engine = ['podman', '--connection', 'podman-machine-default-root']
    network = 'bfm-' + label.lower()
    containers, mounts, volumes = [], [], []
    client = server = None
    server_stopped = False
    network_created = False
    report = dict(status='FAILED', run_id=label, rust_executed=False,
        production_nfs_enabled=False, source_deletion_enabled=False,
        checks=[], cleanup_errors=[], config=config, sources={})
    for name in ('nfs_mount_profile.py', 'check-nfs-mount-profile.py'):
        data = (root / 'scripts' / name).read_bytes()
        report['sources'][name] = dict(sha256=hashlib.sha256(data).hexdigest(), base64=base64.b64encode(data).decode())
    if args.production_gate:
        for name in ('nfs_mount_authorization.py', 'nfs_binding.py', 'nfs_same_share.py', 'nfs_runtime.py', 'nfs_buffered_reads.py', 'nfs_buffered_publication.py', 'nfs_publication.py', 'nfs_buffered_claims.py', 'nfs_buffered_bootstrap.py', 'nfs_bootstrap_state.py', 'nfs_buffered_sync.py', 'nfs_reply_relay.py', 'nfs_reply_proxy.py', 'nfs_rpc.py', 'test_nfs_rpc.py', 'nfs_sync_support.py', 'nfs_syscall_trace.py', 'nfs_sync_capability.py', 'nfs_sync_probe.c', 'nfs_io_trace.py', 'nfs_io_analysis.py', 'test_nfs_io_analysis.py', 'nfs_buffered_commit.py', 'test_nfs_write_resend.py'):
            data = (root / 'scripts' / name).read_bytes()
            report['sources'][name] = dict(sha256=hashlib.sha256(data).hexdigest(), base64=base64.b64encode(data).decode())

    if args.claim_capability or args.claim_loss:
        for name in ('nfs_claim_capability.py', 'test_nfs_claim_capability.py'):
            data = (root / 'scripts' / name).read_bytes()
            report['sources'][name] = dict(sha256=hashlib.sha256(data).hexdigest(), base64=base64.b64encode(data).decode())
    if args.claim_loss:
        for name in ('nfs_claim_recovery.py','test_nfs_claim_recovery.py'):
            data=(root/'scripts'/name).read_bytes()
            report['sources'][name]=dict(sha256=hashlib.sha256(data).hexdigest(),base64=base64.b64encode(data).decode())
    if args.manifest_capability or args.manifest_loss:
        for name in ('nfs_manifest_capability.py', 'test_nfs_manifest_capability.py'):
            data = (root / 'scripts' / name).read_bytes()
            report['sources'][name] = dict(sha256=hashlib.sha256(data).hexdigest(), base64=base64.b64encode(data).decode())

    if args.manifest_loss:
        for name in ('nfs_manifest_recovery.py', 'test_nfs_manifest_recovery.py'):
            data = (root / 'scripts' / name).read_bytes()
            report['sources'][name] = dict(sha256=hashlib.sha256(data).hexdigest(), base64=base64.b64encode(data).decode())

    def run(args, check=True):
        value = subprocess.run(engine + args, capture_output=True, text=True,
                               encoding='utf-8', errors='replace', timeout=45)
        if check and value.returncode:
            raise RuntimeError(str(args) + ': ' + value.stdout + value.stderr)
        return value

    def execute(script, user=None):
        return run(['exec', *(['--user', user] if user else []), client,
                    '/bin/sh', '-eu', '-c', script]).stdout

    def inventory():
        return execute('cat /proc/self/mountinfo')

    def declaration(source='NMP-41B', destination='NMP-41B'):
        return dict(state_path='/tmp/profile-state', **{role: dict(
            path='/tmp/profile-' + role, mountpoint='/tmp/profile-' + role,
            source=address + ':/profile-' + role, addr=address, profile=profile)
            for role, profile in (('source', source), ('destination', destination))})

    def check(name, text, declared, refuse=False, previous=None, scope='live inventory'):
        try:
            result = validate(text, declared, previous)
        except Refused as error:
            if not refuse:
                raise
            result = dict(status='REFUSED', reason=str(error))
        else:
            if refuse:
                raise AssertionError('negative control accepted: ' + name)
        report['checks'].append(dict(name=name, scope=scope, declaration=declared,
                                    inventory=text, result=result, passed=True))
        return result

    def mount(role, extra, timeo=10):
        point = '/tmp/profile-' + role
        run(['exec', client, 'mount', '-i', '-t', 'nfs4', '-o',
             f'addr={address},vers=4.1,proto=tcp,port=2049,sec=sys,timeo={timeo},retrans=1,' + extra,
             address + ':/profile-' + role, point])
        mounts.append(point)

    def unmount_all():
        for point in reversed(mounts.copy()):
            run(['exec', client, 'umount', point])
            mounts.remove(point)

    try:
        image = 'localhost/background-file-mover-e2-nfs'
        report['server_image'] = run(['image', 'inspect', image, '--format', '{{.Id}}']).stdout.strip()
        run(['network', 'create', '--internal', network])
        network_created = True
        volume = network + '-export'
        run(['volume', 'create', volume])
        volumes.append(volume)
        server = run(['create', '--privileged', '--network', network,
                      '--volume', volume + ':/exports', image]).stdout.strip()
        containers.append(server)
        run(['start', server])
        for _ in range(40):
            if 'NFS_READY' in run(['logs', server]).stdout:
                break
            time.sleep(.5)
        else:
            raise RuntimeError('NFS server not ready')
        address = json.loads(run(['inspect', server]).stdout)[0]['NetworkSettings']['Networks'][network]['IPAddress']
        report['server_packages'] = run(['exec', server, 'dpkg-query', '-W', 'nfs-common', 'nfs-kernel-server', 'rpcbind']).stdout
        for role, fsid in (('source', 68), ('destination', 69)):
            size = '128m' if args.claim_loss else '64m' if args.same_share or args.buffered_reads or args.buffered_publication or args.buffered_post_unlink or args.buffered_claims or args.buffered_bootstrap or args.buffered_sync or args.buffered_io or args.buffered_commit or args.buffered_unstable or args.manifest_capability or args.manifest_loss or args.claim_capability else '16m'
            run(['exec', server, '/bin/sh', '-eu', '-c',
                 f'mkdir /exports/profile-{role}; mount -t tmpfs -o size={size},mode=1777 tmpfs /exports/profile-{role}; '
                 f"exportfs -i -o rw,sync,no_subtree_check,root_squash,fsid={fsid} '*:/exports/profile-{role}'"])
        report['server_exports'] = run(['exec', server, 'exportfs', '-v']).stdout
        observer = ['--cap-add', 'SYS_PTRACE', '--cap-add', 'DAC_READ_SEARCH'] if args.buffered_reads or args.buffered_publication or args.buffered_claims or args.buffered_bootstrap or args.buffered_sync or args.buffered_io or args.buffered_commit or args.buffered_unstable or args.manifest_capability or args.manifest_loss or args.claim_capability or args.claim_loss else []
        report['observer_capabilities'] = ['SYS_PTRACE', 'DAC_READ_SEARCH'] if observer else []
        client = run(['create', '--network', network, '--cap-drop', 'all', '--cap-add', 'SYS_ADMIN', *observer,
                      '--security-opt', 'no-new-privileges', '--entrypoint', '/bin/sh',
                      config['runtime'], '-c', 'exec sleep infinity']).stdout.strip()
        containers.append(client)
        run(['start', client])
        report['kernel'] = execute('uname -r').strip()
        report['glibc'] = execute('getconf GNU_LIBC_VERSION').strip()
        assert report['glibc'] == 'glibc 2.22'
        report['mount_namespace'] = execute('readlink /proc/self/ns/mnt').strip()
        execute('mkdir /tmp/profile-source /tmp/profile-destination /tmp/profile-state /tmp/profile-bind; chmod 700 /tmp/profile-state')
        report['client_security'] = execute('cat /proc/1/status')
        for source, destination in (('NMP-41N', 'NMP-41N'), ('NMP-41B', 'NMP-41B'),
                                    ('NMP-41B', 'NMP-41N'), ('NMP-41N', 'NMP-41B')):
            for role, profile in (('source', source), ('destination', destination)):
                mount(role, 'hard,noac' if profile == 'NMP-41N' else 'hard,ac,async')
            text, declared = inventory(), declaration(source, destination)
            result = check(source + '/' + destination, text, declared)
            check('stable same-namespace pin ' + source + '/' + destination, inventory(), declared, previous=result['pin'])
            report.setdefault('io_controls', []).append(execute(
                "umask 077; printf 'mount-profile' >/tmp/profile-source/probe; "
                "cp /tmp/profile-source/probe /tmp/profile-destination/probe; "
                "sha256sum /tmp/profile-source/probe /tmp/profile-destination/probe; "
                "stat -c '%u:%g:%a:%s' /tmp/profile-source/probe /tmp/profile-destination/probe", '1000:1000'))
            unmount_all()
        # Baseline buffered profile for read-only observation and refusal cases.
        mount('source', 'hard,ac,async')
        mount('destination', 'hard,ac,async')
        text, declared = inventory(), declaration()
        baseline = check('buffered baseline', text, declared)
        changed = copy.deepcopy(declared)
        changed['source']['path'] += '/incoming'
        changed['destination'] = dict(changed['source'], path='/tmp/profile-source/received')
        execute('mkdir /tmp/profile-source/incoming /tmp/profile-source/received', '1000:1000')
        check('same-share disjoint directories', inventory(), changed)
        for role in ('source', 'destination'):
            for extra, name in (('soft,ac,async', 'soft'), ('hard,ac,async,ro', 'read-only'),
                                ('hard,ac,async,nocto', 'no close-to-open')):
                unmount_all()
                for selected in ('source', 'destination'):
                    mount(selected, extra if selected == role else 'hard,ac,async')
                check(role + ' ' + name, inventory(), declaration(), refuse=True)
        unmount_all()
        check('both mounts absent/local fallback', inventory(), declaration(), refuse=True)
        mount('source', 'hard,ac,async')
        check('destination mount absent', inventory(), declaration(), refuse=True)
        mount('destination', 'hard,ac,async')
        text = inventory()
        after_remount = check('same-options remount inventory; continuity NOT proven', text, declaration())
        report['remount_pin_reused'] = after_remount['pin'] == baseline['pin']
        unmount_all()
        mount('source', 'hard,ac,async', timeo=20)
        mount('destination', 'hard,ac,async')
        check('changed effective retry option refuses prior pin', inventory(), declaration(), refuse=True, previous=after_remount['pin'])
        for role in ('source', 'destination'):
            execute(f'mkdir -p /tmp/profile-{role}/nested', '1000:1000')
            point = '/tmp/profile-' + role + '/nested'
            run(['exec', client, 'mount', '-t', 'tmpfs', 'tmpfs', point])
            mounts.append(point)
            check(role + ' nested mount', inventory(), declaration(), refuse=True)
            run(['exec', client, 'umount', point])
            mounts.remove(point)
        run(['exec', client, 'mount', '--bind', '/tmp/profile-source/incoming', '/tmp/profile-bind'])
        mounts.append('/tmp/profile-bind')
        changed = declaration()
        changed['source'].update(path='/tmp/profile-bind', mountpoint='/tmp/profile-bind')
        check('subtree bind alias', inventory(), changed, refuse=True)
        run(['exec', client, 'umount', '/tmp/profile-bind'])
        mounts.remove('/tmp/profile-bind')
        changed = declaration()
        changed['source']['path'] += '/incoming'
        changed['state_path'] = '/tmp/profile-source/state'
        check('SQLite state on NFS', inventory(), changed, refuse=True)
        execute('mkdir /tmp/profile-state/nested')
        run(['exec', client, 'mount', '-t', 'tmpfs', 'tmpfs', '/tmp/profile-state/nested'])
        mounts.append('/tmp/profile-state/nested')
        check('nested state mount', inventory(), declaration(), refuse=True)
        run(['exec', client, 'umount', '/tmp/profile-state/nested'])
        mounts.remove('/tmp/profile-state/nested')
        text = inventory()
        # Mutations are parser/model controls, NEVER actual mount/server evidence.
        for old, new, name in (('vers=4.1', 'vers=3', 'NFSv3'), ('vers=4.1', 'vers=4.2', 'NFSv4.2'),
                               ('proto=tcp', 'proto=udp', 'UDP'), ('sec=sys', 'sec=krb5p', 'different security'),
                               ('local_lock=none', 'local_lock=all', 'local-only locks'),
                               ('hard,', 'hard,softreval,', 'cached failure fallback'),
                               ('hard,', 'hard,unknown_semantics=1,', 'unknown effective option'),
                               ('hard,', 'hard,hard,', 'duplicate option'),
                               ('hard,', 'hard,nconnect=2,', 'multiple connections'),
                               ('hard,', 'hard,lookupcache=none,', 'lookup override')):
            assert old in text
            check(name, text.replace(old, new), declaration(), refuse=True, scope='synthetic inventory mutation')
        for key, value in (('addr', '192.0.2.99'), ('source', '192.0.2.99:/foreign'),
                           ('profile', 'undeclared'), ('profile', 'NMP-41N'), ('path', '/tmp/profile-source/../escape')):
            changed = declaration()
            changed['source'][key] = value
            check('declaration mismatch ' + key + '=' + value, text, changed, refuse=True, scope='declaration negative control')
        changed = declaration()
        changed['destination'] = copy.deepcopy(changed['source'])
        check('overlapping roots', text, changed, refuse=True, scope='declaration negative control')
        for malformed in ('', 'bad inventory', text.replace(' rw,', r'\099 rw,', 1), text + text, 'x' * (1024*1024+1)):
            try:
                parse(malformed)
            except Refused:
                report.setdefault('parser_negative_controls', []).append(dict(sha256=hashlib.sha256(malformed.encode()).hexdigest(), passed=True))
            else:
                raise AssertionError('malformed inventory accepted')
        # Kernel escapes/optional fields/longest component match are real parser obligations.
        escaped = '1 2 0:1 / / rw - overlay overlay rw\n3 1 0:2 / /a\\040b rw shared:7 - nfs4 host:/ rw,hard\n'
        assert parse(escaped)[1]['point'] == '/a b'
        from nfs_mount_profile import covering
        assert covering(parse(escaped), '/a b/sub')['id'] == 3
        assert covering(parse(escaped), '/a bc')['id'] == 1
        report['parser_positive_controls'] = ['kernel escape', 'optional fields', 'longest component match', 'prefix collision']
        stable = check('before server outage', inventory(), declaration())
        run(['exec', server, 'rpc.nfsd', '0'])
        server_stopped = True
        assert run(['exec', server, 'cat', '/proc/fs/nfsd/threads']).stdout.strip() == '0'
        started = time.monotonic()
        check('server down still matches inventory; NOT ready/settled', inventory(), declaration(), previous=stable['pin'])
        report['server_down_inventory_seconds'] = time.monotonic() - started
        assert report['server_down_inventory_seconds'] < 5
        run(['exec', server, 'rpc.nfsd', '-G', '10', '-L', '10', '-V', '4', '-p', '2049', '2'])
        server_stopped = False
        time.sleep(11)
        report['restored_io'] = execute('sha256sum /tmp/profile-source/probe /tmp/profile-destination/probe', '1000:1000')
        # Independent capability before Rust: change only VFS flags, preserving
        # the actual mounted NFS root. This must not require unmount/ID changes.
        from nfs_mount_profile import covering
        before = covering(parse(inventory()), '/tmp/profile-source')
        identity = execute("stat -c '%d:%i:%u:%a' /tmp/profile-source", '1000:1000')
        before_pin = validate(inventory(), declaration())['pin']
        run(['exec',client,'mount','-i','-o','remount,bind,nosuid','/tmp/profile-source','/tmp/profile-source'])
        after = covering(parse(inventory()), '/tmp/profile-source')
        assert 'nosuid' in after['vfs'] and {k:v for k,v in before.items() if k!='vfs'} == {k:v for k,v in after.items() if k!='vfs'}
        assert identity == execute("stat -c '%d:%i:%u:%a' /tmp/profile-source", '1000:1000')
        try:
            validate(inventory(), declaration(), previous=before_pin)
        except Refused:
            pass
        else:
            raise AssertionError('changed VFS flag did not refuse original pin')
        restore_flags = ','.join(['remount','bind',*before['vfs']])
        run(['exec',client,'mount','-i','-o',restore_flags,'/tmp/profile-source','/tmp/profile-source'])
        assert covering(parse(inventory()), '/tmp/profile-source') == before
        assert validate(inventory(),declaration(),previous=before_pin)['pin'] == before_pin
        report['vfs_flag_capability'] = dict(passed=True,before=before,changed=after,
                                           root_identity=identity,restored_exact_pin=True)
        if args.production_gate:
            from nfs_mount_authorization import qualify
            report['authorization'] = dict(passed=False, cases=[])
            qualify(root, args.production_gate, args.qualification_gate, run, execute,
                    client, output, mount, unmount_all, mounts, report['authorization'],
                    same_share=args.same_share, buffered_reads=args.buffered_reads,
                    buffered_publication=args.buffered_publication, server=server,
                    buffered_post_unlink=args.buffered_post_unlink, buffered_claims=args.buffered_claims, buffered_bootstrap=args.buffered_bootstrap, buffered_sync=args.buffered_sync, buffered_io=args.buffered_io, buffered_commit=args.buffered_commit, buffered_unstable=args.buffered_unstable, live_loss=args.live_loss, manifest_capability=args.manifest_capability, manifest_loss=args.manifest_loss, claim_capability=args.claim_capability, claim_loss=args.claim_loss,
                    fixture=dict(network=network, containers=containers, mounts=mounts, address=address, config=config))
        report['status'] = 'PASSED'
    except Exception as error:
        report.update(error=f'{type(error).__name__}: {error}', traceback=traceback.format_exc())
    finally:
        if server_stopped:
            try:
                run(['exec', server, 'rpc.nfsd', '-G', '10', '-L', '10', '-V', '4', '-p', '2049', '2'])
                time.sleep(11)
            except Exception as error:
                report['cleanup_errors'].append(str(error))
        if client:
            try:
                unmount_all()
            except Exception as error:
                report['cleanup_errors'].append(str(error))
        if not report['cleanup_errors']:
            if server:
                run(['exec', server, 'rpc.nfsd', '0'], check=False)
                run(['exec', server, 'exportfs', '-au'], check=False)
            for target in reversed(containers):
                if run(['rm', '--force', target], check=False).returncode:
                    report['cleanup_errors'].append('container removal failed: ' + target)
            for volume in volumes:
                if run(['volume', 'rm', volume], check=False).returncode:
                    report['cleanup_errors'].append('volume removal failed: ' + volume)
            if network_created and run(['network', 'rm', network], check=False).returncode:
                report['cleanup_errors'].append('network removal failed: ' + network)
        if report['cleanup_errors']:
            report['status'] = 'FAILED'
            report['recovery_resources'] = dict(containers=containers, mounts=mounts, volumes=volumes, network=network)
        report['rust_executed'] = report.get('authorization',{}).get('rust_executed',False)
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(report['status'] + ': ' + str(output), flush=True)
        if 'error' in report:
            print(report['error'], flush=True)
    return 0 if report['status'] == 'PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
