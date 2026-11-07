"""Finite buffered namespace reply loss; no production/runtime policy changes."""
import hashlib
import json
import time
from nfs_rpc import call, reply


def raw_item(item):
    request=bytes.fromhex(item['request']['payload_hex']); response=bytes.fromhex(item['payload_hex'])
    assert hashlib.sha256(request).hexdigest()==item['request']['sha256']
    assert hashlib.sha256(response).hexdigest()==item['reply_sha256']
    assert call(request)==item['request']['decoded'] and reply(response)==item['reply']
    assert item['xid']==item['request']['decoded']['xid']==item['reply']['xid']


def retry_key(item):
    ops=[dict(o) for o in item['request']['decoded']['operations']]
    assert ops[0]['op']==53
    seq=bytes.fromhex(ops[0]['sequence_hex'])
    assert len(seq)==32 and int.from_bytes(seq[24:28],'big')>=int.from_bytes(seq[20:24],'big')
    assert int.from_bytes(seq[28:32],'big')==1, 'namespace replay requires the observed cachethis=true'
    # Only the highest-slot resource hint may vary; preserve session/sequence/slot/cache policy.
    ops[0]['sequence_hex']=seq[:24].hex()+'00000000'+seq[28:].hex()
    return json.dumps(ops,sort_keys=True)


def validate_claim_resend(row):
    settled=row['settled']; assert not settled['armed'] and not settled['errors']
    assert not settled['released'] and len(settled['dropped'])==1 and settled['connection_resets']
    original=settled['dropped'][0]; raw_item(original); key=retry_key(original)
    assert original['reply']['status']==0
    selected=row['wires'][row['relay_role']]['forwarded']
    assert selected and len({v['receive_id'] for v in selected})==len(selected)
    assert original['connection'] in settled['connection_resets']
    wire=row['wires'][row['relay_role']]['trace']; results=[]
    for item in selected:
        raw_item(item)
        assert item['connection']!=original['connection'] and item['receive_id']!=original['receive_id']
        assert retry_key(item)==key
        request=item['request']['decoded']; response=item['reply']
        assert response['status']==0 and all(o['status']==0 for o in response['operations'])
        assert [o['op'] for o in response['operations']]==[o['op'] for o in request['operations']]
        matches={}
        for direction,digest in (('call',item['request']['sha256']),('reply',item['reply_sha256'])):
            found=[v for v in wire if v['direction']==direction and v['connection']==item['connection']
                   and v['xid']==item['xid'] and v['sha256']==digest]
            assert found
            matches[direction]=min(v['monotonic_ns'] for v in found)
        assert matches['call']<=matches['reply']
        results.append(dict(receive_id=item['receive_id'],connection=item['connection'],
            request_sha256=item['request']['sha256'],reply_sha256=item['reply_sha256'],
            exact_operations=request['operations']==original['request']['decoded']['operations']))
    return dict(kind='cached_namespace_session_replay',cachethis=True,successes=results)


def settle_claim(c,r,action,relay,active,operation,execute,adapted,spawn,output,objects):
    """Kill only owned processes; restart only after actual old-worker exit."""
    if action=='death-drop':
        pid=c.worker; main=r['coordinator_pid']
        r['original_epoch']=json.loads(execute('cat '+c.base+'/state/workers.json','1000:1000'))
        assert r['original_epoch']['group']==int(main)
        c.signal(main,'KILL'); r['dead_coordinator_exit']=c.service.wait(timeout=15)
        assert r['dead_coordinator_exit']!=0
        r['dead_coordinator_exit_state']=c.await_exit(main); assert r['dead_coordinator_exit_state']=='gone'
        assert c.state(pid)=='D'
        path=c.base+'/state/instance.lock'
        before=execute(f"stat -c '%d:%i:%s:%u:%a' {path}",'1000:1000')
        guard=adapted(f'test -f {path}; flock -n -E 73 {path} true','1000:1000',False)
        assert guard.returncode==73 and c.state(pid)=='D'
        assert before==execute(f"stat -c '%d:%i:%s:%u:%a' {path}",'1000:1000')
        r['orphan_guard']=dict(exit_code=73,identity=before,state='D')
        r['worker_fds']=execute(f'ls -l /proc/{pid}/fd')
        assert 'instance.lock' in r['worker_fds'] and 'jobs.sqlite' not in r['worker_fds']
        started=time.monotonic(); status=adapted(c.binary+' --status '+c.config_path,'1000:1000',False)
        r['orphan_status']=dict(exit_code=status.returncode,seconds=time.monotonic()-started,snapshot=json.loads(status.stdout))
        assert status.returncode==2 and r['orphan_status']['snapshot']['phase']=='OwnerUnavailable' and r['orphan_status']['seconds']<5
        contender=spawn('exec '+c.binary+' '+c.config_path,c.label+'-contender'); c.processes.append(contender)
        r['contender_exit']=contender.wait(timeout=6)
        diagnostic=(output/(c.label+'-contender.log')).read_text(encoding='utf-8')
        assert r['contender_exit']!=0 and 'local instance or surviving worker already owns state' in diagnostic
        r['contender_diagnostic']=diagnostic
        r['epoch_after_contender']=json.loads(execute('cat '+c.base+'/state/workers.json','1000:1000'))
        assert r['epoch_after_contender']==r['original_epoch'] and c.state(pid)=='D'
        r['before_drop']=relay.await_held(); assert objects()==r['server_while_withheld']
        c.signal(pid,'KILL'); r['old_worker_state_after_kill']=c.state(pid) or 'gone'
    r['settled']=relay.command('release' if action=='hold-release' else 'drop',operation=operation)
    assert not r['settled']['errors'] and not r['settled']['armed']
    if action=='hold-release': assert r['settled']['released'] and not r['settled']['dropped']
    else:
        assert r['settled']['dropped']==r['before_release']['held'] and not r['settled']['released']
        assert r['settled']['connection_resets']
    for other,item in active.items():
        if item!=relay:item.release()
    if action=='death-drop':
        r['old_worker_exit']=c.await_exit(pid); c.worker=None
        r['server_after_old_exit']=objects(); assert r['server_after_old_exit']==r['server_while_withheld']
        r['pre_restart_wires']={key:item.command('stop_observe',operation=operation) for key,item in active.items()}
        for item in active.values():item.command('observe',operation=operation)
        c.start(False); r['restart_coordinator_pid']=c.service_pid()
        assert r['restart_coordinator_pid']!=main


def confirm_custody(c,r,action):
    samples=[]; r['custody_recovery_samples']=samples; began=time.monotonic()
    for _ in range(18):
        expected=r.get('restart_coordinator_pid',r['coordinator_pid'])
        assert c.service.poll() is None and c.service_pid()==expected
        started=time.monotonic(); health=c.request('GET','/healthz'); hs=time.monotonic()-started
        started=time.monotonic(); status=c.request('GET','/api/v2/jobs/1'); ss=time.monotonic()-started
        started=time.monotonic(); replay=c.request('POST','/api/v2/jobs',c.body); rs=time.monotonic()-started
        sample=dict(elapsed_seconds=time.monotonic()-began,coordinator_pid=expected,health_code=health[0],health_seconds=hs,
            status=status,status_seconds=ss,replay=replay,replay_seconds=rs,
            original_worker_state=c.state(r['paused_worker']['pid']) or 'gone')
        samples.append(sample)
        assert health[0]==status[0]==200 and hs<5 and ss<5 and rs<15
        assert status[1]['details']['condition']!='ReviewRequired' and not status[1]['details']['source_cleanup_enabled']
        if replay[0]==202:
            assert replay[1]['job_id']=='1' and replay[1]['source_paths_released']; return replay
        assert replay[0]==503 and replay[1]['retryable'] and not replay[1]['source_paths_released']
        assert replay[1]['error'] in ('handoff_pending','service_busy')
        time.sleep(1)
    raise AssertionError('custody did not confirm within eighteen bounded same-ID attempts')
