"""Buffered enrolled/populated startup interruption and original-state recovery.

Only owned fixture processes/mounts. No lost-reply or physical durability claim.
"""
import json
import subprocess
import time
from nfs_mount_profile import covering, parse
from nfs_publication import objects
from nfs_runtime import run_runtime
from nfs_bootstrap_state import prepare, local_evidence, source_evidence, destination_evidence, receipt_evidence, partial_evidence, recovered_both


def qualify_buffered_bootstrap(run, execute, client, server, output, mount, unmount_all, report, binaries):
    assert server
    points = ('bootstrap_enrolled', 'bootstrap_populated')
    report['matrix'] = 'buffered-bootstrap'
    engine = ['podman', '--connection', 'podman-machine-default-root']
    execute('umask 077; mkdir /tmp/local', '1000:1000')
    artifacts = {}
    stopped = False
    for profile in ('debug', 'release'):
        execute('cp '+binaries[('qualification', profile)]+' /tmp/qualification-'+profile+'; chmod 555 /tmp/qualification-'+profile)
        artifacts['qualification-'+profile] = report['gates']['qualification']['artifacts'][profile]['sha256']

    def adapted(script, user=None, check=True, target=None):
        assert target in (None, client)
        return run(['exec', *(['--user', user] if user else []), client,
                    '/bin/sh', '-eu', '-c', script], check=check)

    def spawn(script, name, target=None):
        assert target in (None, client)
        with (output/(name+'.log')).open('w', encoding='utf-8') as log:
            return subprocess.Popen(engine+['exec', '--user', '1000:1000', client,
                                            '/bin/sh', '-eu', '-c', script], stdout=log, stderr=log)

    def restore():
        nonlocal stopped
        if stopped:
            run(['exec', server, 'rpc.nfsd', '-G', '10', '-L', '10', '-V', '4', '-p', '2049', '2'])
            time.sleep(11)
            assert run(['exec', server, 'cat', '/proc/fs/nfsd/threads']).stdout.strip() == '2'
            stopped = False

    def status(c, phase):
        began = time.monotonic()
        reply = adapted(c.binary+' --status '+c.config_path, '1000:1000', check=False)
        value = json.loads(reply.stdout)
        elapsed = time.monotonic()-began
        assert elapsed < 5 and reply.returncode in (0, 2)
        if phase is not None:
            assert value['phase'] == phase and reply.returncode == (2 if phase == 'OwnerUnavailable' else 0), value
        return dict(exit_code=reply.returncode, seconds=round(elapsed, 3), snapshot=value)

    def guard(c):
        reply = adapted('flock -n -E 73 '+c.base+'/state/instance.lock true', '1000:1000', check=False)
        assert reply.returncode in (0, 73), reply.stderr
        return dict(contended=reply.returncode == 73, exit_code=reply.returncode)

    def cases(Case):
        nonlocal stopped
        for profile in ('debug', 'release'):
            for point in points:
                print('Buffered startup '+layout+' '+profile+' '+point, flush=True)
                c = Case(profile, point, suffix='-bs-'+layout, both_nfs=True)
                r = c.result
                r.update(layout=layout, config=c.config, scenario_id='SC-110')
                report['cases'].append(r)
                report['rust_executed'] = True
                try:
                    r['inventory'] = execute('cat /proc/self/mountinfo')
                    observed = [covering(parse(r['inventory']), path) for path in (c.source, c.destination)]
                    assert (observed[0] == observed[1]) == (layout == 'same-share')
                    assert all('noac' not in m['super'] for m in observed)
                    assert all(c.config[role+'_binding']['nfs_mount']['profile'] == 'NMP-41B' for role in ('source', 'destination'))
                    r['devices'] = execute(f'stat -c %d {c.source} {c.destination} {c.base}/state', '1000:1000').splitlines()
                    assert (r['devices'][0] == r['devices'][1]) == (layout == 'same-share')
                    assert r['devices'][2] not in r['devices'][:2]
                    r['original_source'] = execute(f"stat -c '%d:%i:%s' {c.source}/current/nested/data.bin; sha256sum {c.source}/current/nested/data.bin", '1000:1000').splitlines()
                    prepare(c, adapted, status, both_nfs=True)
                    r['mountstats_before_outage'] = execute('cat /proc/self/mountstats')
                    assert 'acregmax=60' in r['mountstats_before_outage'] and 'acdirmax=60' in r['mountstats_before_outage']
                    # Fresh fixture mounts explicitly retain ordinary 60-second maxima.
                    stopped = True
                    run(['exec', server, 'rpc.nfsd', '0'])
                    assert run(['exec', server, 'cat', '/proc/fs/nfsd/threads']).stdout.strip() == '0'
                    began = time.monotonic()
                    for _ in range(65):
                        time.sleep(1)
                    r['cache_age_seconds_before_launch'] = round(time.monotonic()-began, 3)
                    assert r['cache_age_seconds_before_launch'] >= 65
                    c.launch(False)
                    for _ in range(12):
                        startup = status(c, None)
                        workers = startup['snapshot']['workers']
                        if startup['snapshot']['phase'] == 'Starting' and len(workers) == 1:
                            c.worker = str(workers[0])
                            break
                        assert c.service.poll() is None
                        time.sleep(.1)
                    else:
                        raise AssertionError('bootstrap worker not assigned')
                    time.sleep(3)
                    assert c.state(c.worker) == 'D' and c.children() == [c.worker]
                    command = execute(f"tr '\\000' ' ' </proc/{c.worker}/cmdline", '1000:1000')
                    assert c.binary in command and '--internal-bootstrap-worker' in command
                    r['bootstrap_worker'] = dict(pid=c.worker, command=command, fixture_pause=False)
                    r['worker_security'] = execute(f'cat /proc/{c.worker}/status', '1000:1000')
                    security = dict(line.split(':', 1) for line in r['worker_security'].splitlines() if ':' in line)
                    assert security['Uid'].split() == security['Gid'].split() == ['1000']*4
                    assert security['NoNewPrivs'].strip() == '1'
                    assert all(int(security[key], 16) == 0 for key in ('CapInh', 'CapPrm', 'CapEff'))
                    raw = execute(f'cat /proc/{c.worker}/syscall').strip()
                    assert len(raw.split()) == 9 and int(raw.split()[0]) >= 0, raw
                    stack = adapted(f'cat /proc/{c.worker}/stack', check=False)
                    wchan = execute(f'cat /proc/{c.worker}/wchan').strip()
                    assert any(word in (stack.stdout+wchan).lower() for word in ('nfs', 'rpc')), (stack.stdout, wchan)
                    r['blocked_bootstrap'] = dict(state='D', syscall=raw, kernel_stack=stack.stdout,
                        stack_exit_code=stack.returncode, stack_diagnostic=stack.stderr, wchan=wchan, nfsd_threads=0)
                    r['startup_status'] = status(c, 'Starting')
                    connected = c.base+'/health-connected'
                    health, health_path = c.request('GET', '/healthz', asynchronous=True, connected_marker=connected)
                    for _ in range(5):
                        if adapted('test -e '+connected, '1000:1000', check=False).returncode == 0:
                            break
                        time.sleep(.1)
                    else:
                        raise AssertionError('startup health request not sent')
                    assert health.poll() is None and not health_path.read_text()
                    r['health_request_connected_and_pending'] = True
                    r['bootstrap_local_while_blocked'] = local_evidence(c, adapted, both_nfs=True)
                    assert r['bootstrap_local_while_blocked'] == r['bootstrap_local_before']
                    epoch_path = c.base+'/state/workers.json'
                    epoch = json.loads(execute('cat '+epoch_path, '1000:1000'))
                    assert epoch['group'] == int(c.service_pid())
                    r['original_epoch'] = epoch
                    r['status_during_outage'] = status(c, 'Starting')
                    assert guard(c)['contended']
                    c.signal(c.service_pid(), 'KILL')
                    assert c.service.wait(timeout=15) != 0
                    r['orphan_samples'] = []
                    for _ in range(2):
                        assert c.state(c.worker) == 'D'
                        sample = dict(guard=guard(c), status=status(c, 'OwnerUnavailable'))
                        assert c.state(c.worker) == 'D'
                        r['orphan_samples'].append(sample)
                    path = output/(c.label+'-contender.json')
                    path.write_text(json.dumps(dict(c.config, bind='127.0.0.1:0')), encoding='utf-8')
                    remote = c.base+'/contender.json'
                    run(['cp', str(path), client+':'+remote])
                    r['contenders'] = []
                    for command, tail in (('', ''), ('--initialize-source ', ''), ('--transfer-one ', ' 1')):
                        began = time.monotonic()
                        reply = adapted(c.binary+' '+command+remote+tail, '1000:1000', check=False)
                        elapsed = time.monotonic()-began
                        assert reply.returncode != 0 and elapsed < 6
                        assert 'local instance or surviving worker already owns state' in reply.stderr, reply.stderr
                        assert c.state(c.worker) == 'D'
                        r['contenders'].append(dict(command=command.strip() or 'service', seconds=round(elapsed, 3), diagnostic=reply.stderr))
                    assert json.loads(execute('cat '+epoch_path, '1000:1000')) == epoch
                    c.signal(c.worker, 'KILL')
                    r['worker_state_after_kill_before_restore'] = c.state(c.worker)
                    restore()
                    r['old_worker_exit'] = c.await_exit(c.worker)
                    for _ in range(30):
                        rows = execute(f'for f in /proc/{c.service_pid()}/task/*/stat /proc/{c.worker}/task/*/stat; do '
                                       'test ! -r "$f" || cat "$f" 2>/dev/null || true; done', '1000:1000').splitlines()
                        tasks = [dict(tid=int(row.split()[0]), state=row.rsplit(') ', 1)[1].split()[0]) for row in rows]
                        if all(t['state'] in ('Z', 'X', 'x') for t in tasks):
                            break
                        time.sleep(.2)
                    else:
                        raise AssertionError('old process still has live threads')
                    r['old_threads_before_recovery'] = tasks
                    c.worker = None
                    assert not guard(c)['contended']
                    r['status_after_exit'] = status(c, 'NoActiveOwner')
                    health.wait(timeout=10)
                    r['interrupted_health_response'] = health_path.read_text(encoding='utf-8')
                    assert '200 OK' not in r['interrupted_health_response']
                    r['health_never_ready_before_recovery'] = True
                    for key, observe in (('local', lambda: local_evidence(c, adapted, both_nfs=True)),
                                         ('source', lambda: source_evidence(c, adapted)),
                                         ('destination', lambda: destination_evidence(c, adapted))):
                        r['bootstrap_'+key+'_after_old_exit'] = observe()
                        assert r['bootstrap_'+key+'_after_old_exit'] == r['bootstrap_'+key+'_before']
                    r['existing_state_preserved_before_recovery'] = True
                    r['re_enrollment_performed'] = False
                    c.start(False)
                    code, handoff = c.request('POST', '/api/v2/jobs', c.body)
                    assert code == 202 and handoff['source_paths_released'] and handoff['job_id'] == '1'
                    r['confirmed_custody_replay'] = [code, handoff]
                    if point == 'bootstrap_enrolled':
                        execute(f"printf 'next recording' >{c.source}/current/nested/data.bin", '1000:1000')
                    r['producer_reuse_after_202'] = True
                    committed = c.recover(restart=False)
                    assert committed['state'] == 'Committed' and not committed['details']['source_cleanup_enabled']
                    expected_attempt = 2 if point == 'bootstrap_populated' else 1
                    assert committed['details']['files'][0]['attempt'] == expected_attempt
                    if point == 'bootstrap_populated':
                        r['partial_after_recovery'] = partial_evidence(c, adapted)
                        assert r['partial_after_recovery'] == r['seed_partial']
                        r['old_partial_preserved'] = True
                    c.verify()
                    after = objects(c, adapted)
                    r['publication_after_recovery'] = after
                    assert after['.staging/COMMITTED.part'] is None
                    assert (after['.staging/1.part'] is not None) == (point == 'bootstrap_populated')
                    assert after['nested/data.bin']['links'] == after['COMMITTED.json']['links'] == 1
                    r['database_identity_after_recovery'] = execute(f"stat -c '%d:%i' {c.base}/state/jobs.sqlite", '1000:1000')
                    r['enrollment_receipt_after_recovery'] = receipt_evidence(c, adapted)
                    assert r['database_identity_after_recovery'] == r['database_identity_before']
                    assert r['enrollment_receipt_after_recovery'] == r['enrollment_receipt_before']
                    recovered_both(c, adapted)
                    replacement = json.loads(execute('cat '+epoch_path, '1000:1000'))
                    assert replacement['group'] == int(c.service_pid()) and replacement['group'] != epoch['group']
                    assert all(replacement[k] == epoch[k] for k in ('version', 'boot', 'namespace', 'guard'))
                    r['replacement_epoch'] = replacement
                    assert c.request('GET', '/api/v2/jobs/2')[0] == 404
                    r['second_job_absent'] = True
                    r['committed'] = committed
                    stop = adapted(c.binary+' --stop '+c.config_path, '1000:1000')
                    assert json.loads(stop.stdout)['phase'] == 'Stopped' and c.service.wait(timeout=30) == 0
                    c.start(False)
                    code, replay = c.request('POST', '/api/v2/jobs', c.body)
                    assert code == 202 and replay['job_id'] == '1' and replay['source_paths_released']
                    assert c.request('GET', '/api/v2/jobs/1')[1]['state'] == 'Committed'
                    assert execute(f'cat {c.source}/current/nested/data.bin', '1000:1000') == 'next recording'
                    assert objects(c, adapted) == after
                    assert execute(f"stat -c '%d:%i' {c.base}/state/jobs.sqlite", '1000:1000') == r['database_identity_before']
                    assert receipt_evidence(c, adapted) == r['enrollment_receipt_before']
                    if point == 'bootstrap_populated':
                        assert partial_evidence(c, adapted) == r['seed_partial']
                    c.verify()
                    r['replay'] = replay
                    r['original_state_bootstrap_recovery_and_producer_bytes_preserved'] = True
                    stop = adapted(c.binary+' --stop '+c.config_path, '1000:1000')
                    assert json.loads(stop.stdout)['phase'] == 'Stopped' and c.service.wait(timeout=30) == 0
                    r['passed'] = True
                finally:
                    c.cleanup()

    try:
        for layout in ('same-share', 'separate-shares'):
            mount('source', 'hard,ac,async,acregmax=60,acdirmax=60')
            if layout == 'separate-shares':
                mount('destination', 'hard,ac,async,acregmax=60,acdirmax=60')
            run_runtime(run, adapted, spawn, restore, server, output, client, artifacts, report,
                        case_runner=cases, nfs_root='/tmp/profile-source',
                        destination_nfs_root='/tmp/profile-destination' if layout == 'separate-shares' else None)
            unmount_all()
        assert len(report['cases']) == 8 and all(c['passed'] for c in report['cases'])
        report['passed'] = True
        report['scope'] = 'Eight buffered same/separate-share enrolled-empty/populated actual blocked startup deaths, surviving-worker exclusion and original-state recovery/replay; one server/joint outage, no RPC completion/reply-loss or physical durability proof.'
    finally:
        restore()
