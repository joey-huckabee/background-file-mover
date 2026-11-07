"""Buffered pre-202 source claim syscall interruption/recovery qualification.

Only owned fixture processes/mounts. No lost-reply or physical durability claim.
"""
import json
import subprocess
import time
from nfs_mount_profile import covering, parse
from nfs_publication import objects, same_object
from nfs_runtime import run_runtime


def qualify_buffered_claims(run, execute, client, server, output, mount, unmount_all, report, binaries):
    assert server
    points = ('claim_link_rpc', 'claim_unlink_rpc')
    report['matrix'] = 'buffered-claims'
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
        assert elapsed < 5 and reply.returncode == (2 if phase == 'OwnerUnavailable' else 0)
        assert value['phase'] == phase, value
        return dict(exit_code=reply.returncode, seconds=round(elapsed, 3), snapshot=value)

    def guard(c):
        reply = adapted('flock -n -E 73 '+c.base+'/state/instance.lock true', '1000:1000', check=False)
        assert reply.returncode in (0, 73), reply.stderr
        return dict(contended=reply.returncode == 73, exit_code=reply.returncode)

    def source_objects(c):
        result = {}
        for name, path in (('producer', c.source+'/current/nested/data.bin'),
                           ('custody', c.source+'/.file-mover/1-0/data')):
            text = execute(f"if test -e {path}; then stat -c '%d:%i:%h:%s' {path}; sha256sum {path}; else echo absent; fi", '1000:1000').splitlines()
            if text == ['absent']:
                result[name] = None
            else:
                device, inode, links, size = map(int, text[0].split(':'))
                result[name] = dict(device=device, inode=inode, links=links, size=size, sha256=text[1].split()[0])
        return result

    def cases(Case):
        nonlocal stopped
        for profile in ('debug', 'release'):
            for point in points:
                print('Buffered source claim '+layout+' '+profile+' '+point, flush=True)
                c = Case(profile, point, suffix='-bc-'+layout, both_nfs=True)
                r = c.result
                r.update(layout=layout, config=c.config, scenario_id='SC-109')
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
                    original = execute(f"stat -c '%d:%i:%s' {c.source}/current/nested/data.bin; sha256sum {c.source}/current/nested/data.bin", '1000:1000')
                    r['original_source'] = original.splitlines()
                    state_command = (f"stat -c '%d:%i' {c.base}/state/jobs.sqlite; "
                                     f'sha256sum {c.config_path} {c.source}/.file-mover/source-enrollment.json')
                    r['original_state'] = execute(state_command, '1000:1000')
                    c.start(True)
                    posted, response_path = c.request('POST', '/api/v2/jobs', c.body, asynchronous=True)
                    c.await_pause()
                    r['worker_security'] = execute(f'cat /proc/{c.worker}/status', '1000:1000')
                    security = dict(line.split(':', 1) for line in r['worker_security'].splitlines() if ':' in line)
                    assert security['Uid'].split() == security['Gid'].split() == ['1000']*4
                    assert security['NoNewPrivs'].strip() == '1'
                    assert all(int(security[key], 16) == 0 for key in ('CapInh', 'CapPrm', 'CapEff'))
                    initial = source_objects(c)
                    r['source_before_outage'] = initial
                    expected = initial['producer']
                    assert expected is not None and expected['sha256'] == r['original_source'][1].split()[0]
                    linking = point == 'claim_link_rpc'
                    if linking:
                        assert initial['custody'] is None and expected['links'] == 1
                    else:
                        assert initial['custody'] == expected and expected['links'] == 2
                    assert adapted(f'test ! -e {c.destination}/1', '1000:1000', check=False).returncode == 0
                    job = c.request('GET', '/api/v2/jobs/1')[1]
                    assert job['state'] == 'Accepted' and not job['source_paths_released']
                    assert not job['details']['source_cleanup_enabled']
                    r['job_before_outage'] = job
                    epoch_path = c.base+'/state/workers.json'
                    epoch = json.loads(execute('cat '+epoch_path, '1000:1000'))
                    assert epoch['group'] == int(c.service_pid())
                    r['original_epoch'] = epoch
                    stopped = True
                    run(['exec', server, 'rpc.nfsd', '0'])
                    assert run(['exec', server, 'cat', '/proc/fs/nfsd/threads']).stdout.strip() == '0'
                    execute('umask 077; : >'+c.rendezvous+'/go', '1000:1000')
                    time.sleep(3)
                    assert c.state(c.worker) == 'D'
                    raw = execute(f'cat /proc/{c.worker}/syscall').strip()
                    fields = raw.split()
                    assert len(fields) == 9 and fields[0] == ('265' if linking else '263'), raw
                    fd = int(fields[1], 16)
                    parent = execute(f'readlink /proc/{c.worker}/fd/{fd}', '1000:1000').strip()
                    assert parent == c.source+'/current/nested', parent
                    blocked = dict(syscall=raw, old_parent=parent, state='D', nfsd_threads=0)
                    if linking:
                        new_fd = int(fields[3], 16)
                        blocked['new_parent'] = execute(f'readlink /proc/{c.worker}/fd/{new_fd}', '1000:1000').strip()
                        assert blocked['new_parent'] == c.source+'/.file-mover/1-0' and int(fields[5], 16) == 0
                    else:
                        assert int(fields[3], 16) == 0
                    r['blocked_claim_syscall'] = blocked
                    r['interruption_kind'] = 'in_flight_linkat_syscall' if linking else 'in_flight_unlinkat_syscall'
                    worker_state = 'D'
                    assert c.children() == [c.worker]
                    began = time.monotonic()
                    assert c.request('GET', '/healthz')[0] == 200
                    r['outage_health_seconds'] = round(time.monotonic()-began, 3)
                    assert r['outage_health_seconds'] < 5
                    began = time.monotonic()
                    assert c.request('GET', '/api/v2/jobs/1')[1] == job
                    r['outage_job_seconds'] = round(time.monotonic()-began, 3)
                    assert r['outage_job_seconds'] < 5
                    r['outage_api_seconds'] = round(r['outage_health_seconds']+r['outage_job_seconds'], 3)
                    posted.wait(timeout=15)
                    response = c.parse(response_path.read_text(encoding='utf-8'))
                    assert response[0] == 503 and response[1]['retryable']
                    assert response[1]['error'] in ('handoff_pending', 'service_busy') and not response[1]['source_paths_released']
                    r['initial_submission'] = dict(exit_code=posted.returncode, response=response)
                    assert c.state(c.worker) == 'D' and c.children() == [c.worker]
                    r['status_during_outage'] = status(c, 'Running')
                    assert guard(c)['contended']
                    c.signal(c.service_pid(), 'KILL')
                    assert c.service.wait(timeout=15) != 0
                    r['orphan_samples'] = []
                    for _ in range(2):
                        assert c.state(c.worker).upper() == worker_state
                        sample = dict(guard=guard(c), status=status(c, 'OwnerUnavailable'))
                        assert c.state(c.worker).upper() == worker_state
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
                        assert c.state(c.worker).upper() == worker_state
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
                    assert execute(state_command, '1000:1000') == r['original_state']
                    observed = source_objects(c)
                    r['source_after_old_exit'] = observed
                    aliases = [obj for obj in observed.values() if obj is not None]
                    assert aliases
                    for obj in aliases:
                        same_object(obj, expected)
                        assert obj['links'] == len(aliases)
                    assert adapted(f'test ! -e {c.destination}/1', '1000:1000', check=False).returncode == 0
                    c.start(False)
                    code, handoff = c.request('POST', '/api/v2/jobs', c.body)
                    assert code == 202 and handoff['source_paths_released'] and handoff['job_id'] == '1'
                    r['confirmed_custody_replay'] = [code, handoff]
                    # Producer reuse is permitted only AFTER confirmed custody/202.
                    execute(f"printf 'next recording' >{c.source}/current/nested/data.bin", '1000:1000')
                    r['producer_reuse_after_202'] = True
                    committed = c.recover(restart=False)
                    assert committed['state'] == 'Committed' and not committed['details']['source_cleanup_enabled']
                    assert committed['details']['files'][0]['attempt'] == 1
                    c.verify()
                    after = objects(c, adapted)
                    r['publication_after_recovery'] = after
                    custody = source_objects(c)['custody']
                    same_object(custody, expected)
                    assert custody['links'] == 1
                    r['source_after_recovery'] = source_objects(c)
                    assert after['.staging/1.part'] is None and after['.staging/COMMITTED.part'] is None
                    assert after['nested/data.bin']['links'] == after['COMMITTED.json']['links'] == 1
                    assert execute(f"stat -c '%d:%i:%s' {c.source}/.file-mover/1-0/data", '1000:1000').strip() == r['original_source'][0]
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
                    assert execute(state_command, '1000:1000') == r['original_state']
                    c.verify()
                    r['replay'] = replay
                    r['original_state_claim_inode_and_producer_bytes_preserved'] = True
                    stop = adapted(c.binary+' --stop '+c.config_path, '1000:1000')
                    assert json.loads(stop.stdout)['phase'] == 'Stopped' and c.service.wait(timeout=30) == 0
                    r['passed'] = True
                finally:
                    c.cleanup()

    try:
        for layout in ('same-share', 'separate-shares'):
            mount('source', 'hard,ac,async')
            if layout == 'separate-shares':
                mount('destination', 'hard,ac,async')
            run_runtime(run, adapted, spawn, restore, server, output, client, artifacts, report,
                        case_runner=cases, nfs_root='/tmp/profile-source',
                        destination_nfs_root='/tmp/profile-destination' if layout == 'separate-shares' else None)
            unmount_all()
        assert len(report['cases']) == 8 and all(c['passed'] for c in report['cases'])
        report['passed'] = True
        report['scope'] = 'Eight buffered same/separate-share pre-202 blocked source linkat/unlinkat deaths, orphan exclusion and original-state custody recovery/delivery/replay; no RPC completion/reply-loss or physical durability proof.'
    finally:
        restore()
