"""Finite buffered, same-mount service crash cases in the owned profile fixture.

Uses existing qualification pauses after returned durable LINK operations. No
RPC loss, outage, remote-settlement, physical durability or production claim.
"""
import json
import subprocess
from nfs_mount_profile import covering, parse
from nfs_runtime import run_runtime


def qualify_same_share(run, execute, client, output, mount, unmount_all, report, binaries):
    engine = ['podman', '--connection', 'podman-machine-default-root']
    mount('source', 'hard,ac,async')
    execute('umask 077; mkdir /tmp/local', '1000:1000')
    artifacts = {}
    for profile in ('debug', 'release'):
        binary = binaries[('qualification', profile)]
        execute('cp '+binary+' /tmp/qualification-'+profile+'; chmod 555 /tmp/qualification-'+profile)
        artifacts['qualification-'+profile] = report['gates']['qualification']['artifacts'][profile]['sha256']

    def adapted_execute(script, user=None, check=True, target=None):
        assert target in (None, client)
        return run(['exec', *(['--user', user] if user else []), client,
                    '/bin/sh', '-eu', '-c', script], check=check)

    def spawn(script, name, target=None):
        assert target in (None, client)
        with (output/(name+'.log')).open('w', encoding='utf-8') as log:
            return subprocess.Popen(engine+['exec', '--user', '1000:1000', client,
                                            '/bin/sh', '-eu', '-c', script], stdout=log, stderr=log)

    def cases(Case):
        for profile in ('debug', 'release'):
            for point in ('baseline', 'claim_link', 'file_link'):
                print('Same-share '+profile+' '+point, flush=True)
                c = Case(profile, point, suffix='-buffered-same-share', both_nfs=True)
                r = c.result
                report['cases'].append(r)
                report['rust_executed'] = True
                try:
                    r['config'] = c.config
                    r['inventory'] = execute('cat /proc/self/mountinfo')
                    mounts = [covering(parse(r['inventory']), path) for path in (c.source, c.destination)]
                    assert mounts[0] == mounts[1] and mounts[0]['point'] == '/tmp/profile-source'
                    assert 'noac' not in mounts[0]['super']
                    assert all(c.config[role+'_binding']['nfs_mount']['profile'] == 'NMP-41B'
                               for role in ('source', 'destination'))
                    assert c.config['source_binding']['root_id'] != c.config['destination_binding']['root_id']
                    assert not c.destination.startswith(c.source+'/') and not c.source.startswith(c.destination+'/')
                    devices = execute(f'stat -c %d {c.source} {c.destination} {c.base}/state', '1000:1000').splitlines()
                    assert devices[0] == devices[1] and devices[0] != devices[2]
                    r['filesystem_devices'] = devices
                    original = execute(f"stat -c '%d:%i:%s' {c.source}/current/nested/data.bin", '1000:1000')
                    state_command = (f"stat -c '%d:%i' {c.base}/state/jobs.sqlite; "
                                     f'sha256sum {c.config_path} {c.source}/.file-mover/source-enrollment.json')
                    r['original_local_state'] = execute(state_command, '1000:1000')
                    c.start(point != 'baseline')
                    if point == 'baseline':
                        status = c.recover(restart=False)
                    else:
                        posted, response = c.request('POST', '/api/v2/jobs', c.body, asynchronous=True)
                        c.await_pause()
                        r['worker_security'] = execute(f'cat /proc/{c.worker}/status', '1000:1000')
                        security = dict(line.split(':', 1) for line in r['worker_security'].splitlines() if ':' in line)
                        assert security['Uid'].split() == ['1000'] * 4 and security['NoNewPrivs'].strip() == '1'
                        assert all(int(security[key], 16) == 0 for key in ('CapInh', 'CapPrm', 'CapEff'))
                        r['owned_aliases_before_crash'] = c.owned_aliases()
                        r['status_before_crash'] = c.request('GET', '/api/v2/jobs/1')[1]
                        execute(f'test ! -e {c.destination}/1/COMMITTED.json', '1000:1000')
                        r['manifest_absent_before_crash'] = True
                        assert r['status_before_crash']['source_paths_released'] == (point == 'file_link')
                        if point == 'file_link':
                            assert posted.wait(timeout=10) == 0
                            reply = c.parse(response.read_text(encoding='utf-8'))
                            assert reply[0] == 202 and reply[1]['source_paths_released']
                            r['handoff_before_crash'] = reply
                            execute(f"printf 'next recording' >{c.source}/current/nested/data.bin", '1000:1000')
                        c.signal(c.worker, 'STOP')
                        assert c.state(c.worker) in ('T', 't')
                        c.signal(c.service_pid(), 'KILL')
                        r['coordinator_exit_code'] = c.service.wait(timeout=15)
                        assert r['coordinator_exit_code'] != 0 and c.state(c.worker) in ('T', 't')
                        r['worker_survived_coordinator_stopped'] = True
                        c.signal(c.worker, 'KILL')
                        r['worker_exit_before_restart'] = c.await_exit(c.worker)
                        posted.wait(timeout=15)
                        r['original_request_wire'] = response.read_text(encoding='utf-8')
                        if point == 'claim_link' and r['original_request_wire'].startswith('HTTP/'):
                            assert c.parse(r['original_request_wire'])[0] != 202
                        assert c.owned_aliases() == r['owned_aliases_before_crash']
                        status = c.recover()
                    assert status['state'] == 'Committed' and not status['details']['source_cleanup_enabled']
                    if point != 'file_link':
                        execute(f"printf 'next recording' >{c.source}/current/nested/data.bin", '1000:1000')
                    assert execute(f"stat -c '%d:%i:%s' {c.source}/.file-mover/1-0/data", '1000:1000') == original
                    r['private_source_identity'] = execute(f"stat -c '%d:%i:%h:%s' {c.source}/.file-mover/1-0/data", '1000:1000').strip()
                    assert r['private_source_identity'].split(':')[2] == '1'
                    r['destination_identity'] = execute(f"stat -c '%d:%i:%h:%s' {c.destination}/1/nested/data.bin", '1000:1000').strip()
                    final = r['destination_identity'].split(':')
                    assert final[0] == original.split(':')[0] and final[1] != original.split(':')[1]
                    assert final[2] == '1'
                    if point == 'file_link':
                        assert final[:2] == r['owned_aliases_before_crash'][0].split(':')[:2]
                    c.verify()
                    r['committed'] = status
                    r['claimed_source_identity'] = original.strip()
                    manifest_hash = execute(f'sha256sum {c.destination}/1/COMMITTED.json', '1000:1000').split()[0]
                    stop = adapted_execute(c.binary+' --stop '+c.config_path, '1000:1000')
                    r['stop_before_replay'] = json.loads(stop.stdout)
                    assert r['stop_before_replay']['phase'] == 'Stopped' and c.service.wait(timeout=30) == 0
                    assert execute(state_command, '1000:1000') == r['original_local_state']
                    c.start(False)
                    code, replay = c.request('POST', '/api/v2/jobs', c.body)
                    assert code == 202 and replay['job_id'] == '1' and replay['source_paths_released']
                    assert c.request('GET', '/api/v2/jobs/1')[1]['state'] == 'Committed'
                    assert execute(f'cat {c.source}/current/nested/data.bin', '1000:1000') == 'next recording'
                    assert execute(f'sha256sum {c.destination}/1/COMMITTED.json', '1000:1000').split()[0] == manifest_hash
                    assert execute(f"stat -c '%d:%i:%h:%s' {c.destination}/1/nested/data.bin", '1000:1000').strip() == r['destination_identity']
                    assert execute(f"stat -c '%d:%i:%h:%s' {c.source}/.file-mover/1-0/data", '1000:1000').strip() == r['private_source_identity']
                    assert execute(state_command, '1000:1000') == r['original_local_state']
                    c.verify()
                    r['committed_replay'] = replay
                    r['manifest_sha256'] = manifest_hash
                    r['new_producer_bytes_untouched'] = True
                    r['same_original_state_recovered'] = True
                    stop = adapted_execute(c.binary+' --stop '+c.config_path, '1000:1000')
                    assert json.loads(stop.stdout)['phase'] == 'Stopped' and c.service.wait(timeout=30) == 0
                    r['passed'] = True
                finally:
                    c.cleanup()

    run_runtime(run, adapted_execute, spawn, lambda: None, None, output, client,
                artifacts, report, case_runner=cases, nfs_root='/tmp/profile-source')
    unmount_all()
    assert len(report['cases']) == 6 and all(c['passed'] for c in report['cases'])
    report['passed'] = True
    report['scope'] = 'Buffered NMP-41B, disjoint private roots on one mount/export, local state; two baselines and four coordinator/worker crashes after durable claim/file LINK. No outage, RPC reply loss or physical durability proof.'
