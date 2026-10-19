"""Buffered worker sync/RPC observations and conditional native capability proof.

Fixture-only tracing/relay/probe. Does not qualify service reply-loss or durability.
"""
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from nfs_bootstrap_state import receipt_evidence
from nfs_mount_profile import covering, parse
from nfs_reply_relay import ReplyRelay
from nfs_runtime import run_runtime
from nfs_sync_capability import validate_resend
from nfs_sync_support import build_probe, start_trace, finish_trace, correlate


def qualify_buffered_sync(run, execute, client, server, output, unmount_all, report, binaries, fixture, io_trace=False):
    root = Path(__file__).resolve().parent
    config, containers = fixture['config'], fixture['containers']
    report.update(matrix='buffered-io' if io_trace else 'buffered-sync', capabilities=[], relays={})
    tests = subprocess.run([sys.executable, str(root/'test_nfs_rpc.py'), '-v'], capture_output=True, text=True, timeout=20)
    report['decoder_tests'] = dict(passed=tests.returncode == 0, output=tests.stdout+tests.stderr)
    assert tests.returncode == 0
    if io_trace:
        tests = subprocess.run([sys.executable, str(root/'test_nfs_io_analysis.py'), '-v'], capture_output=True, text=True, timeout=20)
        report['io_analysis_tests'] = dict(passed=tests.returncode == 0, output=tests.stdout+tests.stderr)
        assert tests.returncode == 0
    engine = ['podman', '--connection', 'podman-machine-default-root']
    execute('umask 077; mkdir /tmp/local /tmp/sync-probes', '1000:1000')
    artifacts = {}
    for profile in ('debug', 'release'):
        execute('cp '+binaries[('qualification', profile)]+' /tmp/qualification-'+profile+'; chmod 555 /tmp/qualification-'+profile)
        artifacts['qualification-'+profile] = report['gates']['qualification']['artifacts'][profile]['sha256']

    def adapted(script, user=None, check=True, target=None):
        assert target in (None, client)
        return run(['exec', *(['--user', user] if user else []), client, '/bin/sh', '-eu', '-c', script], check=check)

    def spawn(script, name, target=None):
        assert target in (None, client)
        with (output/(name+'.log')).open('w', encoding='utf-8') as log:
            return subprocess.Popen(engine+['exec', '--user', '1000:1000', '--env', 'LD_BIND_NOW=1', client,
                                            '/bin/sh', '-eu', '-c', script], stdout=log, stderr=log)

    relays = {role: ReplyRelay(run, fixture['network'], config['builder'], fixture['address'], containers, output)
              for role in ('source', 'destination')}
    for role, relay in relays.items():
        report['relays'][role] = dict(relay.evidence, security=run(['exec', relay.container, 'cat', '/proc/1/status']).stdout)
    if not io_trace: report['probe'] = build_probe(run, output, client, containers, config)

    def clocks(observer, active):
        actors = [client, observer, *{v.container for v in active.values()}]
        rows = {actor: run(['exec', actor, 'readlink', '/proc/self/ns/time']).stdout.strip() for actor in actors}
        assert all(value.startswith('time:[') for value in rows.values()) and len(set(rows.values())) == 1, rows
        return rows

    def mount(role):
        point = '/tmp/profile-'+role
        ip = relays[role].address
        run(['exec', client, 'mount', '-i', '-t', 'nfs4', '-o',
             'addr='+ip+',vers=4.1,proto=tcp,port=2049,sec=sys,hard,timeo=10,retrans=1,ac,async', ip+':/profile-'+role, point])
        fixture['mounts'].append(point)

    def windows(active, action):
        return {role: relay.command(action) for role, relay in active.items()}

    def join_wire(wires):
        return dict(trace=[dict(entry, relay_role=role) for role, wire in wires.items() for entry in wire['trace']],
                    trace_bytes=sum(w['trace_bytes'] for w in wires.values()),
                    trace_overflow=any(w['trace_overflow'] for w in wires.values()),
                    errors=[e for w in wires.values() for e in w['errors']])

    def operations(syncs):
        return sorted({op['op'] for s in syncs for call in s['rpc_calls'] if call['decoded']
                       for op in call['decoded']['operations'] if op['op'] in (5, 38)})

    def cases(Case):
        for profile in ('debug', 'release'):
            for point, role in (('claim_apply', 'source'), ('copy_chunk', 'destination')):
                print('Buffered sync '+layout+' '+profile+' '+point, flush=True)
                c = Case(profile, point, suffix='-sy-'+layout, both_nfs=True)
                r = c.result
                r.update(layout=layout, config=c.config, role=role, scenario_id='SC-111')
                report['cases'].append(r); report['rust_executed'] = True
                active = {'source': relays['source']} if layout == 'same-share' else relays
                try:
                    r['inventory'] = execute('cat /proc/self/mountinfo')
                    mounts = [covering(parse(r['inventory']), path) for path in (c.source, c.destination)]
                    assert (mounts[0] == mounts[1]) == (layout == 'same-share')
                    assert all('noac' not in m['super'] and 'sync' not in m['super'] for m in mounts)
                    assert all(c.config[k+'_binding']['nfs_mount']['profile'] == 'NMP-41B' for k in ('source', 'destination'))
                    r['devices'] = execute(f'stat -c %d {c.source} {c.destination} {c.base}/state', '1000:1000').splitlines()
                    assert (r['devices'][0] == r['devices'][1]) == (layout == 'same-share')
                    assert r['devices'][2] not in r['devices'][:2]
                    r['original_source'] = execute(f"stat -c '%d:%i:%s' {c.source}/current/nested/data.bin; sha256sum {c.source}/current/nested/data.bin", '1000:1000').splitlines()
                    c.start(True)
                    posted, response_path = c.request('POST', '/api/v2/jobs', c.body, asynchronous=True)
                    c.await_pause(); pid = c.worker
                    assert execute(f'ls /proc/{pid}/task', '1000:1000').split() == [pid]
                    r['worker_security'] = execute(f'cat /proc/{pid}/status', '1000:1000')
                    security = dict(line.split(':', 1) for line in r['worker_security'].splitlines() if ':' in line)
                    assert security['Uid'].split() == security['Gid'].split() == ['1000']*4
                    assert security['NoNewPrivs'].strip() == '1' and all(int(security[k], 16) == 0 for k in ('CapInh','CapPrm','CapEff'))
                    r['database_before'] = execute(f"stat -c '%d:%i' {c.base}/state/jobs.sqlite", '1000:1000')
                    r['enrollment_before'] = receipt_evidence(c, adapted)
                    observer = start_trace(run, client, int(pid), containers, config,
                                           expected_exit='supervised-delivery' if point == 'copy_chunk' else 'zero', io=io_trace)
                    r['clock_namespaces'] = clocks(observer, active)
                    windows(active, 'observe')
                    execute('touch '+c.rendezvous+'/go', '1000:1000')
                    r['worker_exit'] = c.await_exit(pid); c.worker = None
                    trace = finish_trace(run, observer)
                    wires = windows(active, 'stop_observe')
                    r['wire'] = wires
                    r['trace'] = correlate(trace, join_wire(wires))
                    if io_trace:
                        from nfs_io_analysis import analyze
                        r['io_analysis'] = analyze(trace, wires)
                    if point == 'copy_chunk':
                        code, receipt = c.request('GET', '/api/v2/jobs/1')
                        assert code == 200 and receipt['state'] == 'Committed' and receipt['details']['files'][0]['attempt'] == 1
                        r['retirement_committed_receipt'] = receipt
                    prefix = c.source if role == 'source' else c.destination
                    syncs = [s for s in trace['syncs'] if s['path'].startswith(prefix+'/')]
                    assert syncs and all(s['result'] == 0 for s in syncs)
                    r['nfs_syncs'] = syncs
                    r['observed_sync_operations'] = operations(syncs)
                    mount_ids = {m['id'] for m in mounts}
                    r['full_nfs_sync_operations'] = operations([s for s in trace['syncs'] if int(s['mount_id']) in mount_ids])
                    r['undecoded_sync_calls'] = sum(call['decoded'] is None for s in syncs for call in s['rpc_calls'])
                    posted.wait(timeout=15); initial = c.parse(response_path.read_text(encoding='utf-8'))
                    r['initial_response'] = initial
                    assert (initial[0] == 202 and initial[1]['source_paths_released']) or (initial[0] == 503 and initial[1]['retryable'] and not initial[1]['source_paths_released'])
                    code, accepted = c.request('POST', '/api/v2/jobs', c.body)
                    assert code == 202 and accepted['job_id'] == '1' and accepted['source_paths_released']
                    r['confirmed_response'] = [code, accepted]
                    execute(f"printf 'next recording' >{c.source}/current/nested/data.bin", '1000:1000')
                    final = c.recover(restart=False); c.verify()
                    r['source_identity_after'] = execute(f"stat -c '%d:%i:%s' {c.source}/.file-mover/1-0/data", '1000:1000').strip()
                    assert r['source_identity_after'] == r['original_source'][0]
                    r['database_after'] = execute(f"stat -c '%d:%i' {c.base}/state/jobs.sqlite", '1000:1000')
                    r['enrollment_after'] = receipt_evidence(c, adapted)
                    assert r['database_after'] == r['database_before'] and r['enrollment_after'] == r['enrollment_before']
                    assert final['details']['files'][0]['attempt'] == 1 and not final['details']['source_cleanup_enabled']
                    assert execute(f'cat {c.source}/current/nested/data.bin', '1000:1000') == 'next recording'
                    assert c.request('GET', '/api/v2/jobs/2')[0] == 404
                    r.update(committed=final, producer_reuse_after_202=True, source_and_state_preserved=True, service_sync_loss_tested=False)
                    stopped = adapted(c.binary+' --stop '+c.config_path, '1000:1000')
                    assert json.loads(stopped.stdout)['phase'] == 'Stopped' and c.service.wait(timeout=30) == 0
                    r['passed'] = True
                finally:
                    for relay in active.values(): relay.release()
                    c.cleanup()

    def capability(layout, observed):
        # One client may send both exports' traffic through one established
        # transport. Observe every active relay, never infer it from mount addr.
        active = {'source': relays['source']} if layout == 'same-share' else relays
        mountpoint = '/tmp/profile-source' if layout == 'same-share' else '/tmp/profile-destination'
        export = '/exports/profile-source' if layout == 'same-share' else '/exports/profile-destination'
        result = dict(layout=layout, service_observed_operations=observed, observations=[], withholding=[], passed=False)
        report['capabilities'].append(result)
        counter = 0
        def probe(label, operation=None, relay_role=None):
            nonlocal counter
            relay = relays[relay_role] if relay_role is not None else None
            counter += 1
            base = '/tmp/sync-probes/'+layout+'-'+str(counter)
            target = mountpoint+'/sync-'+layout+'-'+str(counter)
            remote = target.replace(mountpoint, export, 1)
            process = spawn(f'exec /tmp/nfs-sync-probe dirty {target} {base}.ready {base}.go', 'sync-'+layout+'-'+label)
            row = dict(label=label, operation=operation, relay_role=relay_role, target=target, passed=False)
            result['observations' if operation is None else 'withholding'].append(row)
            try:
                for _ in range(30):
                    ready = adapted('cat '+base+'.ready', '1000:1000', check=False)
                    if ready.returncode == 0: break
                    assert process.poll() is None; time.sleep(.1)
                else: raise AssertionError('sync probe did not become ready')
                pid, fd = map(int, ready.stdout.split()); row.update(pid=pid, fd=fd)
                observer = start_trace(run, client, pid, containers, config) if operation is None else None
                if observer: row['clock_namespaces'] = clocks(observer, active)
                windows(active, 'observe')
                if operation is not None: relay.command('arm', None, operation)
                execute('touch '+base+'.go', '1000:1000')
                if operation is not None:
                    row['held'] = relay.await_held()
                    raw = execute(f'cat /proc/{pid}/syscall').strip()
                    assert raw.split()[0] == '74' and int(raw.split()[1],16) == fd
                    assert execute(f'cat /proc/{pid}/stat').rsplit(') ',1)[1].split()[0] == 'D'
                    row['native_syscall'] = raw
                    row['pending_fd_path'] = execute(f'readlink /proc/{pid}/fd/{fd}').strip()
                    assert row['pending_fd_path'] == target
                    row['server_sha256_while_withheld'] = run(['exec',server,'sha256sum',remote]).stdout.split()[0]
                    row['server_identity_while_withheld'] = run(['exec',server,'stat','-c','%d:%i:%h:%s',remote]).stdout.strip()
                    assert row['server_sha256_while_withheld'] == hashlib.sha256(b'S'*4096).hexdigest()
                    row['server_threads'] = run(['exec',server,'cat','/proc/fs/nfsd/threads']).stdout.strip()
                    assert row['server_threads'] == '2'
                    row['before_release_or_drop'] = relay.await_held()
                    row['settled'] = relay.command(label)
                assert process.wait(timeout=30) == 0
                row['wires'] = windows(active, 'stop_observe')
                row['wire'] = join_wire(row['wires'])
                if relay is not None: row['wire']['forwarded'] = row['wires'][relay_role]['forwarded']
                if observer:
                    row['trace'] = correlate(finish_trace(run, observer), row['wire'])
                    row['observed_sync_operations'] = operations(row['trace']['syncs'])
                row['probe_output'] = (output/('sync-'+layout+'-'+label+'.log')).read_text(encoding='utf-8')
                assert 'fsync returned 0' in row['probe_output']
                if operation is not None:
                    if label == 'drop': row['resend_validation'] = validate_resend(row, operation)
                    row['server_identity_after'] = run(['exec',server,'stat','-c','%d:%i:%h:%s',remote]).stdout.strip()
                    row['server_sha256_after'] = run(['exec',server,'sha256sum',remote]).stdout.split()[0]
                    assert row['server_identity_after'] == row['server_identity_while_withheld']
                    assert row['server_sha256_after'] == row['server_sha256_while_withheld']
                row['passed'] = True
            finally:
                for item in active.values(): item.release()
                if process.poll() is None:
                    adapted('touch '+base+'.go', '1000:1000', check=False)
                    process.wait(timeout=30)
            print('Buffered native sync '+layout+' '+label+': PASS', flush=True)
            return row
        discovery = probe('discovery')
        candidates = sorted(set(observed)&set(discovery['observed_sync_operations']))
        result['available_operations'] = candidates
        if candidates:
            selected = 5 if 5 in candidates else 38
            relay_role = next(call['relay_role'] for sync in discovery['trace']['syncs'] for call in sync['rpc_calls']
                              if call['decoded'] and any(op['op'] == selected for op in call['decoded']['operations']))
            result['selected_relay_role'] = relay_role
            for action in ('release','drop'): probe(action, selected, relay_role)
            result['withholding_available'] = True
        else:
            result.update(withholding_available=False, limitation='No common decoded service/native WRITE or COMMIT inside sync; no invented positive withholding case.')
        result['passed'] = True

    try:
        for layout in ('same-share','separate-shares'):
            mount('source')
            if layout == 'separate-shares': mount('destination')
            run_runtime(run, adapted, spawn, lambda: None, server, output, client, artifacts, report,
                        case_runner=cases, nfs_root='/tmp/profile-source',
                        destination_nfs_root='/tmp/profile-destination' if layout == 'separate-shares' else None)
            observed = sorted({op for c in report['cases'] if c['layout'] == layout for op in c['full_nfs_sync_operations']})
            if not io_trace: capability(layout, observed)
            unmount_all()
        assert len(report['cases']) == 8 and all(c['passed'] for c in report['cases'])
        assert len(report['capabilities']) == (0 if io_trace else 2) and all(c['passed'] for c in report['capabilities'])
        report.update(passed=True, scope=('Eight healthy buffered worker I/O traces with descriptor/filehandle/payload attribution; no native controls, service faults or physical durability.' if io_trace else 'Eight healthy buffered worker traces with actual clock identity and bounded syscall/RPC correlation; conditional native OS sync release/drop proof, not service sync-loss or physical durability.'))
    finally:
        for role, relay in relays.items():
            relay.release()
            report['relays'][role]['final_state'] = relay.state(strict=False)
