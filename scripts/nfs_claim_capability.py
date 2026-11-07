"""Buffered actual-claim success controls and optional finite live/death reply loss."""
import hashlib
import json
import subprocess
import time
from nfs_bootstrap_state import receipt_evidence
from nfs_mount_profile import covering, parse
from nfs_reply_relay import ReplyRelay, server_objects
from nfs_runtime import run_runtime
from nfs_rpc import call, reply


def claim_proof(state, operation, before, completed):
    """Require matched whole-compound success and independently observed aliases."""
    assert operation in (11, 28) and state['operation'] == operation and state['armed']
    assert len(state['held']) == 1 and not any(state[k] for k in ('forwarded', 'released', 'dropped', 'errors'))
    item = state['held'][0]
    request, response = item['request']['decoded'], item['reply']
    raw_request = bytes.fromhex(item['request']['payload_hex'])
    raw_response = bytes.fromhex(item['payload_hex'])
    assert hashlib.sha256(raw_request).hexdigest() == item['request']['sha256'] and call(raw_request) == request
    assert hashlib.sha256(raw_response).hexdigest() == item['reply_sha256'] and reply(raw_response) == response
    assert item['xid'] == request['xid'] == response['xid']
    assert response['status'] == 0
    assert [o['op'] for o in request['operations']] == [o['op'] for o in response['operations']]
    assert all(o['status'] == 0 for o in response['operations'])
    selected = [o for o in request['operations'] if o['op'] == operation]
    assert len(selected) == 1 and selected[0]['name'] == ('data' if operation == 11 else 'data.bin')
    assert request['operations'][0]['op'] == 53
    assert any(o['op'] == 22 for o in request['operations'])
    assert before['old']['links'] == 1 and before['final'] is None
    assert completed['final']['links'] == (2 if operation == 11 else 1)
    assert completed['old'] == (completed['final'] if operation == 11 else None)
    assert all(completed['final'][k] == before['old'][k] for k in ('device', 'inode', 'size', 'sha256'))
    return dict(operation=operation, name=selected[0]['name'], receive_id=item['receive_id'],
                request_operations=[o['op'] for o in request['operations']],
                request_sha256=item['request']['sha256'], reply_sha256=item['reply_sha256'])


def qualify_claims(run, execute, client, server, output, unmount_all, report, binaries, fixture, loss=False):
    report.update(matrix='claim-loss' if loss else 'claim-capability', relays={},
        declared_cases='Eight actual source-claim LINK/REMOVE success hold/release controls: two operations, two share layouts, debug/release. No reply discard or coordinator death.')
    if loss:
        from nfs_claim_recovery import settle_claim, confirm_custody, validate_claim_resend
        report['declared_cases']='Twenty-four actual workers: eight successful-reply release controls, eight live drops, eight coordinator-death drops; both buffered layouts/profiles and claim operations.'
    execute('umask 077; mkdir /tmp/local', '1000:1000')
    artifacts = {}
    for profile in ('debug', 'release'):
        execute('cp '+binaries['qualification', profile]+' /tmp/qualification-'+profile+'; chmod 555 /tmp/qualification-'+profile)
        artifacts['qualification-'+profile] = report['gates']['qualification']['artifacts'][profile]['sha256']
    def adapted(script, user=None, check=True, target=None):
        assert target in (None, client)
        return run(['exec', *(['--user', user] if user else []), client, '/bin/sh', '-eu', '-c', script], check=check)
    def spawn(script, name, target=None):
        assert target in (None, client)
        with (output/(name+'.log')).open('w', encoding='utf-8') as log:
            return subprocess.Popen(['podman', '--connection', 'podman-machine-default-root', 'exec', '--user', '1000:1000',
                '--env', 'LD_BIND_NOW=1', client, '/bin/sh', '-eu', '-c', script], stdout=log, stderr=log)
    relays = {role: ReplyRelay(run, fixture['network'], fixture['config']['builder'], fixture['address'], fixture['containers'], output)
              for role in ('source', 'destination')}
    for role, relay in relays.items():
        report['relays'][role] = dict(relay.evidence, security=run(['exec', relay.container, 'cat', '/proc/1/status']).stdout)
    def cases(Case):
        for action in (('hold-release','live-drop','death-drop') if loss else ('hold-release',)):
            for profile in ('debug', 'release'):
                for point, operation in (('claim_link_rpc', 11), ('claim_unlink_rpc', 28)):
                    c = Case(profile, point, suffix='-claim-'+layout+'-'+action, both_nfs=True)
                    r = c.result
                    r.update(layout=layout, operation=operation, scenario_id='SC-118' if action.endswith('drop') else 'SC-117', action=action, config=c.config)
                    report['cases'].append(r); report['rust_executed'] = True
                    print('Claim capability '+layout+' '+profile+' '+point+' '+action, flush=True)
                    source_remote = c.source.replace('/tmp/profile-source/', '/exports/profile-source/', 1)
                    old, private = source_remote+'/current/nested/data.bin', source_remote+'/.file-mover/1-0/data'
                    def objects(): return server_objects(run, server, old, private)
                    try:
                        r['inventory'] = execute('cat /proc/self/mountinfo')
                        roots = [covering(parse(r['inventory']), p) for p in (c.source, c.destination)]
                        assert (roots[0] == roots[1]) == (layout == 'same-share')
                        assert all(c.config[k+'_binding']['nfs_mount']['profile'] == 'NMP-41B' for k in ('source', 'destination'))
                        r['server_before_submission'] = objects()
                        c.start(True)
                        posted, response_path = c.request('POST', '/api/v2/jobs', c.body, asynchronous=True)
                        c.await_pause(); pid = c.worker
                        r['coordinator_pid'] = c.service_pid()
                        r['worker_security'] = execute(f'cat /proc/{pid}/status', '1000:1000')
                        sec = dict(l.split(':', 1) for l in r['worker_security'].splitlines() if ':' in l)
                        assert sec['Uid'].split() == sec['Gid'].split() == ['1000']*4 and sec['NoNewPrivs'].strip() == '1'
                        assert sec['Threads'].strip() == '1' and sec['PPid'].strip() == r['coordinator_pid']
                        assert all(int(sec[k], 16) == 0 for k in ('CapInh', 'CapPrm', 'CapEff'))
                        r['database_before'] = execute(f"stat -c '%d:%i' {c.base}/state/jobs.sqlite", '1000:1000')
                        r['enrollment_before'] = receipt_evidence(c, adapted)
                        for relay in active.values(): relay.command('observe', operation=operation)
                        for relay in active.values(): relay.command('arm', 'data' if operation == 11 else 'data.bin', operation)
                        execute('touch '+c.rendezvous+'/go', '1000:1000')
                        for _ in range(40):
                            roles = [role for role, relay in active.items() if relay.state()['held']]
                            if roles: break
                            time.sleep(.1)
                        assert len(roles) == 1
                        role = roles[0]; relay = active[role]
                        r['relay_role'] = role; r['held'] = relay.await_held()
                        raw = execute(f'cat /proc/{pid}/syscall').strip(); words = raw.split()
                        assert len(words) == 9 and int(words[0]) == (265 if operation == 11 else 263)
                        fd = int(words[1], 16)
                        parent = execute(f'readlink /proc/{pid}/fd/{fd}').strip()
                        assert parent == c.source+'/current/nested' and c.state(pid) == 'D'
                        r['pending'] = dict(syscall=raw, state='D', parent=parent, fdinfo=execute(f'cat /proc/{pid}/fdinfo/{fd}'))
                        r['server_parent_inode'] = run(['exec', server, 'stat', '-c', '%i', source_remote+'/current/nested']).stdout.strip()
                        if operation == 11:
                            newfd = int(words[3], 16)
                            r['pending']['new_parent'] = execute(f'readlink /proc/{pid}/fd/{newfd}').strip()
                            r['pending']['new_fdinfo'] = execute(f'cat /proc/{pid}/fdinfo/{newfd}')
                            r['server_new_parent_inode'] = run(['exec', server, 'stat', '-c', '%i', source_remote+'/.file-mover/1-0']).stdout.strip()
                            assert r['pending']['new_parent'] == c.source+'/.file-mover/1-0' and int(words[5], 16) == 0
                        else: assert int(words[3], 16) == 0
                        r['server_while_withheld'] = objects()
                        r['proof'] = claim_proof(r['held'], operation, r['server_before_submission'], r['server_while_withheld'])
                        r['nfsd_threads'] = run(['exec', server, 'cat', '/proc/fs/nfsd/threads']).stdout.strip()
                        assert r['nfsd_threads'] == '2'
                        for key, method, path, body in (('health', 'GET', '/healthz', None), ('during', 'GET', '/api/v2/jobs/1', None),
                                                       ('held_replay', 'POST', '/api/v2/jobs', c.body)):
                            started = time.monotonic(); response = c.request(method, path, body)
                            r[key] = dict(response=response, seconds=time.monotonic()-started)
                            assert r[key]['seconds'] < (15 if key == 'held_replay' else 5)
                        assert r['health']['response'][0] == 200
                        status = r['during']['response'][1]
                        assert r['during']['response'][0] == 200 and status['state'] == 'Accepted' and not status['source_paths_released']
                        assert not status['details']['source_cleanup_enabled']
                        posted.wait(timeout=15); r['initial_submission'] = c.parse(response_path.read_text(encoding='utf-8'))
                        for reply in (r['initial_submission'], r['held_replay']['response']):
                            assert reply[0] == 503 and reply[1]['retryable'] and not reply[1]['source_paths_released']
                            assert reply[1]['error'] in ('handoff_pending', 'service_busy')
                        assert c.children() == [pid] and c.state(pid) == 'D' and c.service.poll() is None
                        r['destination_absent'] = adapted(f'test ! -e {c.destination}/1', '1000:1000', False).returncode == 0
                        assert r['destination_absent'] and objects() == r['server_while_withheld']
                        r['before_release'] = relay.await_held()
                        assert claim_proof(r['before_release'], operation, r['server_before_submission'], objects()) == r['proof']
                        if loss:
                            settle_claim(c,r,action,relay,active,operation,execute,adapted,spawn,output,objects)
                            r['confirmed_custody']=confirm_custody(c,r,action)
                        else:
                            r['settled']=relay.command('release',operation=operation)
                            assert r['settled']['released'] and not r['settled']['dropped']
                            for other,item in active.items():
                                if other!=role:item.release()
                            r['confirmed_custody']=c.request('POST','/api/v2/jobs',c.body)
                        assert r['confirmed_custody'][0] == 202 and r['confirmed_custody'][1]['source_paths_released']
                        assert r['confirmed_custody'][1]['job_id'] == '1'
                        execute(f"printf 'next recording' >{c.source}/current/nested/data.bin", '1000:1000')
                        final = c.recover(False); c.verify()
                        r['wires'] = {key: item.command('stop_observe', operation=operation) for key, item in active.items()}
                        if action=='live-drop':r['resend_validation']=validate_claim_resend(r)
                        assert c.service_pid()==r.get('restart_coordinator_pid',r['coordinator_pid'])
                        assert final['state'] == 'Committed' and final['details']['files'][0]['attempt'] == 1
                        assert not final['details']['source_cleanup_enabled']
                        r['server_after'] = objects()
                        assert r['server_after']['final']['links'] == 1
                        assert all(r['server_after']['final'][k] == r['server_before_submission']['old'][k] for k in ('device', 'inode', 'size', 'sha256'))
                        assert execute(f'cat {c.source}/current/nested/data.bin', '1000:1000') == 'next recording'
                        r['database_after'] = execute(f"stat -c '%d:%i' {c.base}/state/jobs.sqlite", '1000:1000')
                        r['enrollment_after'] = receipt_evidence(c, adapted)
                        assert r['database_before'] == r['database_after'] and r['enrollment_before'] == r['enrollment_after']
                        assert c.request('GET', '/api/v2/jobs/2')[0] == 404
                        stopped = adapted(c.binary+' --stop '+c.config_path, '1000:1000')
                        assert json.loads(stopped.stdout)['phase'] == 'Stopped' and c.service.wait(timeout=30) == 0
                        r['coordinator_exit_state'] = c.await_exit(c.service_pid()); c.worker = None
                        r.update(committed=final, passed=True, producer_reuse_after_202=True, service_reply_loss_tested=action.endswith('drop'))
                        print('Claim capability '+layout+' '+profile+' '+point+' '+action+': PASS', flush=True)
                    finally:
                        for relay in active.values(): relay.release()
                        c.cleanup()
    try:
        for layout in ('same-share', 'separate-shares'):
            active = {'source': relays['source']} if layout == 'same-share' else relays
            for role, relay in active.items():
                point = '/tmp/profile-'+role; ip = relay.address
                run(['exec', client, 'mount', '-i', '-t', 'nfs4', '-o',
                     'addr='+ip+',vers=4.1,proto=tcp,port=2049,sec=sys,hard,timeo=10,retrans=1,ac,async', ip+':/profile-'+role, point])
                fixture['mounts'].append(point)
            run_runtime(run, adapted, spawn, lambda: None, server, output, client, artifacts, report, case_runner=cases,
                        nfs_root='/tmp/profile-source', destination_nfs_root='/tmp/profile-destination' if layout == 'separate-shares' else None)
            unmount_all()
        assert len(report['cases']) == (24 if loss else 8) and all(c['passed'] for c in report['cases'])
        report.update(passed=True, scope='Eight repeated claim controls and sixteen finite live/death namespace loss recoveries; no general NAS/kernel/power or delayed-settlement qualification.' if loss else 'Eight buffered actual-claim LINK/REMOVE successful-reply hold/release controls. No discarded reply, coordinator death, NAS, original SLES kernel, power durability or remote-settlement qualification.')
    finally:
        for role, relay in relays.items():
            relay.release(); report['relays'][role]['final_state'] = relay.state(strict=False)
