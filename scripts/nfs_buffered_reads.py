"""Actual buffered payload-read blockage/death/recovery in the owned NFS lab."""
import hashlib
import json
import subprocess
import time
from nfs_mount_profile import covering, parse
from nfs_runtime import run_runtime


def qualify_buffered_reads(run, execute, client, server, output, mount, unmount_all, report, binaries):
    assert server
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

    def local_status(c, phase):
        began = time.monotonic()
        reply = adapted(c.binary+' --status '+c.config_path, '1000:1000', check=False)
        value = json.loads(reply.stdout)
        elapsed = time.monotonic()-began
        assert elapsed < 5 and reply.returncode in (0, 2) and value['phase'] == phase, (reply.stderr, value)
        return dict(exit_code=reply.returncode, seconds=round(elapsed, 3), snapshot=value)

    def guard(c):
        reply = adapted('flock -n -E 73 '+c.base+'/state/instance.lock true', '1000:1000', check=False)
        assert reply.returncode in (0, 73), reply.stderr
        return dict(contended=reply.returncode == 73, exit_code=reply.returncode)

    def cases(Case):
        nonlocal stopped
        for profile in ('debug', 'release'):
            for point in ('source_copy', 'verify_read'):
                print('Buffered reads '+layout+' '+profile+' '+point, flush=True)
                c = Case(profile, point, suffix='-buffered-'+layout, both_nfs=True)
                r = c.result
                r.update(layout=layout, config=c.config, scenario_id='SC-106')
                report['cases'].append(r)
                report['rust_executed'] = True
                try:
                    r['inventory'] = execute('cat /proc/self/mountinfo')
                    observed = [covering(parse(r['inventory']), path) for path in (c.source, c.destination)]
                    assert (observed[0] == observed[1]) == (layout == 'same-share')
                    assert all('noac' not in m['super'] for m in observed)
                    assert all(c.config[role+'_binding']['nfs_mount']['profile'] == 'NMP-41B'
                               for role in ('source', 'destination'))
                    devices = execute(f'stat -c %d {c.source} {c.destination} {c.base}/state', '1000:1000').splitlines()
                    assert (devices[0] == devices[1]) == (layout == 'same-share')
                    assert devices[2] not in devices[:2]
                    r['devices'] = devices
                    r['original_source'] = execute(f"stat -c '%d:%i:%s' {c.source}/current/nested/data.bin; sha256sum {c.source}/current/nested/data.bin", '1000:1000').splitlines()
                    state_command = (f"stat -c '%d:%i' {c.base}/state/jobs.sqlite; "
                                     f'sha256sum {c.config_path} {c.source}/.file-mover/source-enrollment.json')
                    r['original_state'] = execute(state_command, '1000:1000')
                    c.start(True)
                    code, handoff = c.request('POST', '/api/v2/jobs', c.body)
                    assert code == 202 and handoff['source_paths_released'] and handoff['job_id'] == '1'
                    r['handoff'] = handoff
                    execute(f"printf 'next recording' >{c.source}/current/nested/data.bin", '1000:1000')
                    c.await_pause()
                    r['status_before_outage'] = c.request('GET', '/api/v2/jobs/1')[1]
                    assert r['status_before_outage']['state'] == 'Claimed'
                    assert r['status_before_outage']['details']['files'][0]['transfer_phase'] == ('Intent' if point == 'source_copy' else 'Copied')
                    stage = c.destination+'/1/.staging/1.part'
                    r['staging_before_outage'] = execute(f"stat -c '%d:%i:%s' {stage}", '1000:1000').strip()
                    size = int(r['staging_before_outage'].split(':')[-1])
                    assert size == (1048576 if point == 'source_copy' else 2*1048576+17)
                    assert execute(f"stat -c '%d:%i:%s' {c.source}/.file-mover/1-0/data", '1000:1000').strip() == r['original_source'][0]
                    execute(f'test ! -e {c.destination}/1/COMMITTED.json', '1000:1000')
                    r['manifest_absent_before_outage'] = True
                    # Never hash the target after its cache advice/rendezvous.
                    epoch_path = c.base+'/state/workers.json'
                    epoch = json.loads(execute('cat '+epoch_path, '1000:1000'))
                    assert epoch['group'] == int(c.service_pid())
                    r['original_epoch'] = epoch
                    stopped = True
                    run(['exec', server, 'rpc.nfsd', '0'])
                    assert run(['exec', server, 'cat', '/proc/fs/nfsd/threads']).stdout.strip() == '0'
                    execute('umask 077; : >'+c.rendezvous+'/go', '1000:1000')
                    time.sleep(3)
                    assert c.state(c.worker) == 'D' and c.children() == [c.worker]
                    execute('test ! -e '+c.rendezvous+'/read-completed', '1000:1000')
                    syscall = execute(f'cat /proc/{c.worker}/syscall').strip()
                    fields = syscall.split()
                    assert len(fields) == 9 and fields[0] == '0' and int(fields[3], 16) == 1048576, syscall
                    descriptor = int(fields[1], 16)
                    target = execute(f'readlink /proc/{c.worker}/fd/{descriptor}', '1000:1000').strip()
                    assert target == (c.source+'/.file-mover/1-0/data' if point == 'source_copy' else stage), target
                    r['blocked_read'] = dict(syscall=syscall, fd=descriptor, target=target, state='D', nfsd_threads=0, read_completed=False)
                    security = execute(f'cat /proc/{c.worker}/status', '1000:1000')
                    values = dict(line.split(':', 1) for line in security.splitlines() if ':' in line)
                    assert values['Uid'].split() == ['1000']*4 and values['NoNewPrivs'].strip() == '1'
                    assert all(int(values[key], 16) == 0 for key in ('CapInh', 'CapPrm', 'CapEff'))
                    r['worker_security'] = security
                    began = time.monotonic()
                    assert c.request('GET', '/healthz')[0] == 200
                    r['outage_health_seconds'] = round(time.monotonic()-began, 3)
                    assert r['outage_health_seconds'] < 5
                    assert c.request('GET', '/api/v2/jobs/1')[1] == r['status_before_outage']
                    r['status_during_outage'] = local_status(c, 'Running')
                    assert guard(c)['contended']
                    c.signal(c.service_pid(), 'KILL')
                    assert c.service.wait(timeout=15) != 0
                    r['orphan_samples'] = []
                    for _ in range(2):
                        assert c.state(c.worker) == 'D'
                        sample = dict(guard=guard(c), status=local_status(c, 'OwnerUnavailable'))
                        assert c.state(c.worker) == 'D' and sample['status']['exit_code'] == 2
                        r['orphan_samples'].append(sample)
                    # Logical epoch, not raw flock closure, authorizes refusal.
                    competitor = dict(c.config, bind='127.0.0.1:0')
                    path = output/(c.label+'-contender.json')
                    path.write_text(json.dumps(competitor), encoding='utf-8')
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
                    execute('test ! -e '+c.rendezvous+'/read-completed', '1000:1000')
                    restore()
                    r['old_worker_exit'] = c.await_exit(c.worker)
                    c.worker = None
                    assert not guard(c)['contended']
                    r['status_after_exit'] = local_status(c, 'NoActiveOwner')
                    assert execute(state_command, '1000:1000') == r['original_state']
                    r['staging_after_exit'] = execute(f"stat -c '%d:%i:%s' {stage}; sha256sum {stage}", '1000:1000').splitlines()
                    assert r['staging_after_exit'][0].split(':')[:2] == r['staging_before_outage'].split(':')[:2]
                    after_size = int(r['staging_after_exit'][0].split(':')[-1])
                    assert size <= after_size <= 2*1048576+17
                    expected = bytes(min(after_size, 2*1048576))+b'0123456789abcdefg'[:max(0,after_size-2*1048576)]
                    assert r['staging_after_exit'][1].split()[0] == hashlib.sha256(expected).hexdigest()
                    execute(f'test ! -e {c.destination}/1/COMMITTED.json', '1000:1000')
                    committed = c.recover()
                    assert committed['state'] == 'Committed' and not committed['details']['source_cleanup_enabled']
                    assert committed['details']['files'][0]['attempt'] == (2 if point == 'source_copy' else 1)
                    c.verify()
                    r['committed'] = committed
                    assert execute(state_command, '1000:1000') == r['original_state']
                    assert execute(f"stat -c '%d:%i:%s' {c.source}/.file-mover/1-0/data", '1000:1000').strip() == r['original_source'][0]
                    r['final_identity'] = execute(f"stat -c '%d:%i' {c.destination}/1/nested/data.bin", '1000:1000').strip()
                    assert r['final_identity'] != ':'.join(r['original_source'][0].split(':')[:2])
                    if point == 'source_copy':
                        assert execute(f"stat -c '%d:%i:%s' {stage}; sha256sum {stage}", '1000:1000').splitlines() == r['staging_after_exit']
                        assert r['final_identity'] != ':'.join(r['staging_before_outage'].split(':')[:2])
                        r['old_partial_preserved'] = True
                    else:
                        assert r['final_identity'] == ':'.join(r['staging_before_outage'].split(':')[:2])
                        r['verified_allocation_preserved'] = True
                    manifest_hash = execute(f'sha256sum {c.destination}/1/COMMITTED.json', '1000:1000').split()[0]
                    stop = adapted(c.binary+' --stop '+c.config_path, '1000:1000')
                    assert json.loads(stop.stdout)['phase'] == 'Stopped' and c.service.wait(timeout=30) == 0
                    c.start(False)
                    code, replay = c.request('POST', '/api/v2/jobs', c.body)
                    assert code == 202 and replay['job_id'] == '1' and replay['source_paths_released']
                    assert c.request('GET', '/api/v2/jobs/1')[1]['state'] == 'Committed'
                    assert execute(f'cat {c.source}/current/nested/data.bin', '1000:1000') == 'next recording'
                    assert execute(f'sha256sum {c.destination}/1/COMMITTED.json', '1000:1000').split()[0] == manifest_hash
                    assert execute(f"stat -c '%d:%i' {c.destination}/1/nested/data.bin", '1000:1000').strip() == r['final_identity']
                    assert execute(state_command, '1000:1000') == r['original_state']
                    c.verify()
                    r['replay'] = replay
                    r['original_state_and_producer_bytes_preserved'] = True
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
        report['scope'] = 'Eight buffered same/separate-export read(2) blockage, coordinator death, orphan exclusion and original-state recovery/replay cases; one server/joint outage, no RPC reply-loss, server reboot or power-durability proof.'
    finally:
        restore()
