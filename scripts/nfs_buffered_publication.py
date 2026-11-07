"""Buffered publication namespace/pre-sync crash/recovery qualification.

Only owned fixture processes/mounts. No lost-reply or physical durability claim.
"""
import json
import subprocess
import time
from nfs_mount_profile import covering, parse
from nfs_publication import objects, same_object
from nfs_runtime import run_runtime


def qualify_buffered_publication(run, execute, client, server, output, mount, unmount_all, report, binaries, post_unlink=False):
    assert server
    points = ('file_unlink_sync', 'manifest_unlink_sync') if post_unlink else (
        'file_link_sync', 'file_unlink', 'manifest_link_sync', 'manifest_unlink')
    expected_cases = 8 if post_unlink else 16
    report['matrix'] = 'buffered-post-unlink' if post_unlink else 'buffered-publication'
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

    def cases(Case):
        nonlocal stopped
        for profile in ('debug', 'release'):
            for point in points:
                print('Buffered publication '+layout+' '+profile+' '+point, flush=True)
                c = Case(profile, point, suffix=('-bpu-' if post_unlink else '-bp-')+layout, both_nfs=True)
                r = c.result
                r.update(layout=layout, config=c.config, scenario_id='SC-108' if post_unlink else 'SC-107')
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
                    code, handoff = c.request('POST', '/api/v2/jobs', c.body)
                    assert code == 202 and handoff['source_paths_released'] and handoff['job_id'] == '1'
                    r['handoff'] = handoff
                    execute(f"printf 'next recording' >{c.source}/current/nested/data.bin", '1000:1000')
                    c.await_pause()
                    r['worker_security'] = execute(f'cat /proc/{c.worker}/status', '1000:1000')
                    security = dict(line.split(':', 1) for line in r['worker_security'].splitlines() if ':' in line)
                    assert security['Uid'].split() == ['1000']*4 and security['NoNewPrivs'].strip() == '1'
                    assert all(int(security[key], 16) == 0 for key in ('CapInh', 'CapPrm', 'CapEff'))
                    initial = objects(c, adapted)
                    r['publication_before_outage'] = initial
                    manifest = point.startswith('manifest')
                    active_old = '.staging/COMMITTED.part' if manifest else '.staging/1.part'
                    active_new = 'COMMITTED.json' if manifest else 'nested/data.bin'
                    expected = initial[active_new]
                    assert expected is not None
                    if post_unlink:
                        assert initial[active_old] is None and expected['links'] == 1
                        r['staging_absent_before_directory_sync'] = True
                    else:
                        assert initial[active_old] == expected and expected['links'] == 2
                    payload = initial['nested/data.bin']
                    assert payload['sha256'] == r['original_source'][1].split()[0]
                    if manifest:
                        assert initial['.staging/1.part'] is None and payload['links'] == 1
                        c.verify()  # Visible manifest must already describe complete payload.
                    else:
                        assert initial['COMMITTED.json'] is None and initial['.staging/COMMITTED.part'] is None
                    job = c.request('GET', '/api/v2/jobs/1')[1]
                    assert job['state'] == 'Claimed' and not job['details']['source_cleanup_enabled']
                    assert job['details']['files'][0]['attempt'] == 1
                    assert job['details']['files'][0]['transfer_phase'] == ('Published' if manifest else 'PublishIntent')
                    r['job_before_outage'] = job
                    code, replay = c.request('POST', '/api/v2/jobs', c.body)
                    r['replay_before_outage'] = dict(code=code, response=replay)
                    assert code == 202 and replay['job_id'] == '1' and replay['source_paths_released']
                    epoch_path = c.base+'/state/workers.json'
                    epoch = json.loads(execute('cat '+epoch_path, '1000:1000'))
                    assert epoch['group'] == int(c.service_pid())
                    r['original_epoch'] = epoch
                    stopped = True
                    run(['exec', server, 'rpc.nfsd', '0'])
                    assert run(['exec', server, 'cat', '/proc/fs/nfsd/threads']).stdout.strip() == '0'
                    actual_unlink = point.endswith('_unlink')
                    if actual_unlink:
                        execute('umask 077; : >'+c.rendezvous+'/go', '1000:1000')
                        time.sleep(3)
                        assert c.state(c.worker) == 'D'
                        raw = execute(f'cat /proc/{c.worker}/syscall').strip()
                        fields = raw.split()
                        assert len(fields) == 9 and fields[0] == '263' and int(fields[3], 16) == 0, raw
                        fd = int(fields[1], 16)
                        target = execute(f'readlink /proc/{c.worker}/fd/{fd}', '1000:1000').strip()
                        assert target == c.destination+'/1/.staging', target
                        r['blocked_unlink'] = dict(syscall=raw, fd=fd, parent=target, state='D', nfsd_threads=0)
                        r['interruption_kind'] = 'in_flight_unlinkat_syscall'
                    else:
                        execute('test ! -e '+c.rendezvous+'/go', '1000:1000')
                        c.signal(c.worker, 'STOP')
                        assert c.state(c.worker) in ('T', 't')
                        r['interruption_kind'] = ('unlink_returned_following_directory_sync_not_called' if post_unlink
                                                  else 'link_returned_following_sync_not_called')
                        r['pause_unreleased_before_crash'] = True
                        r['worker_stopped_before_crash'] = c.state(c.worker)
                    worker_state = 'D' if actual_unlink else 'T'
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
                    observed = objects(c, adapted)
                    r['publication_after_old_exit'] = observed
                    same_object(observed[active_new], expected)
                    if post_unlink:
                        assert observed[active_old] is None and observed[active_new]['links'] == 1
                        r['staging_absent_after_old_exit'] = True
                    aliases = [observed[n] for n in (active_old, active_new) if observed[n] is not None]
                    for obj in aliases:
                        same_object(obj, expected)
                        assert obj['links'] == len(aliases)
                    if not manifest:
                        assert observed['COMMITTED.json'] is None
                    committed = c.recover()
                    assert committed['state'] == 'Committed' and not committed['details']['source_cleanup_enabled']
                    assert committed['details']['files'][0]['attempt'] == 1
                    c.verify()
                    after = objects(c, adapted)
                    r['publication_after_recovery'] = after
                    same_object(after[active_new], expected)
                    same_object(after['nested/data.bin'], payload)
                    assert after['.staging/1.part'] is None and after['.staging/COMMITTED.part'] is None
                    assert after['nested/data.bin']['links'] == after['COMMITTED.json']['links'] == 1
                    assert execute(f"stat -c '%d:%i:%s' {c.source}/.file-mover/1-0/data", '1000:1000').strip() == r['original_source'][0]
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
                    r['original_state_publications_and_producer_bytes_preserved'] = True
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
        assert len(report['cases']) == expected_cases and all(c['passed'] for c in report['cases'])
        report['passed'] = True
        report['scope'] = ('Eight buffered same/separate-export file/manifest staging-unlink-returned before-directory-sync process crashes, orphan exclusion and original-state recovery/replay; no pending-sync/RPC reply-loss or power-durability proof.' if post_unlink else
                           'Sixteen buffered same/separate-export file/manifest returned-LINK pre-sync or blocked unlinkat deaths, orphan exclusion, original-state recovery/replay; one server/joint outage, no RPC reply-loss or power-durability proof.')
    finally:
        restore()
