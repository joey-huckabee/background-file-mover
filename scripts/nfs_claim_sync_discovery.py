"""Exact actual-worker source-claim fsync entry/exit capability controls."""
import json
import time
from nfs_sync_support import start_trace, finish_trace


def qualify(Case,run,execute,client,server,output,containers,config,relay,state,restore,snapshot,report):
    def clock():
        return int(run(['exec',relay.container,'python3','-c','import time; print(time.monotonic_ns())']).stdout)

    def custody(c,phase):
        base='/e/profile-source/'+c.label+'/source'
        paths=[base+'/current/nested/data.bin',base+'/.file-mover/1-0/data']
        lines=run(['exec','--user','1000:1000',report['storage_reader'],'/bin/sh','-eu','-c',
                   "stat -c '%d:%i:%h:%s' "+' '.join(paths)+'; sha256sum '+' '.join(paths)+'; test ! -e /e/profile-destination/'+c.label+'/destination/1']).stdout.splitlines()
        assert len(lines)==4
        rows={name:dict(identity=lines[i],sha256=lines[2+i].split()[0]) for i,name in enumerate(('original','private'))}
        assert rows['original']==rows['private'] and rows['private']['identity'].split(':')[2:]==['2','2097169']
        rows['delivery_absent']=True
        return rows

    def gate_file(observer,name):
        value=run(['exec',observer,'cat','/tmp/sync-gate/'+name+'.json'],False)
        return json.loads(value.stdout) if value.returncode==0 else None

    for profile in ('debug','release'):
        for phase in ('file','directory'):
            for mode in ('healthy','nfsd-stopped'):
                print('Claim fsync '+profile+' '+phase+' '+mode,flush=True)
                point='claim_link_rpc'
                c=Case(profile,point,suffix='-sync-'+phase+'-'+mode,both_nfs=True)
                r=c.result;report['mover_cases'].append(r);report['rust_executed']=True
                r.update(scenario_id='SC-133',phase=phase,mode=mode,config=c.config,
                         layout='two distinct retained tmpfs/client NFS filesystems, local state')
                observer=None;down=False
                try:
                    original=c.source+'/current/nested/data.bin'
                    local="stat -c '%d:%i' "+c.base+'/state/jobs.sqlite; sha256sum '+c.config_path
                    enrollment='sha256sum '+c.source+'/.file-mover/source-enrollment.json'
                    r['local_before']=execute(local,'1000:1000').stdout
                    r['enrollment_before']=execute(enrollment,'1000:1000').stdout
                    relay.command('observe');c.start(True)
                    posted=c.request('POST','/api/v2/jobs',c.body,asynchronous=True)
                    c.await_pause();r['coordinator_pid']=c.service_pid();r['worker_pid']=c.worker
                    target=c.source+'/.file-mover/1-0'+('/data' if phase=='file' else '')
                    observer=start_trace(run,client,c.worker,containers,config,expected_exit='zero',io=True,gate=dict(path=target))
                    r['clock_namespaces']={x:run(['exec',x,'readlink','/proc/self/ns/time']).stdout.strip() for x in (client,observer,relay.container)}
                    assert len(set(r['clock_namespaces'].values()))==1
                    execute(': >'+c.rendezvous+'/go','1000:1000')
                    for _ in range(25):
                        selected=gate_file(observer,'entry')
                        if selected:break
                        assert c.service.poll() is None;time.sleep(.1)
                    else:raise AssertionError('source-claim fsync entry not intercepted')
                    r['entry']=selected;assert selected['syscall']==74 and selected['descriptor']['path']==target
                    r['entry_worker_state']=c.state(c.worker);assert r['entry_worker_state'] in ('t','T')
                    r['status_before']=c.request('GET','/api/v2/jobs/1')[1]
                    assert r['status_before']['state']=='Accepted'
                    r['epoch_before']=json.loads(execute('cat '+c.base+'/state/workers.json','1000:1000').stdout)
                    r['custody_before']=custody(c,phase);r['before_server']=state()
                    if mode=='nfsd-stopped':
                        run(['exec',server,'rpc.nfsd','0']);down=True;r['stopped_server']=state()
                        assert r['stopped_server']['threads']=='0'
                        r['custody_stopped']=custody(c,phase);assert r['custody_stopped']==r['custody_before']
                    r['worker_security']=execute(f'cat /proc/{c.worker}/status').stdout
                    r['guard_exit']=execute('flock -n -E 73 '+c.base+'/state/instance.lock true','1000:1000',False).returncode
                    assert r['guard_exit']==73
                    r['before_wire']=relay.command('checkpoint')
                    r['entry_release_ns']=clock();run(['exec',observer,'touch','/tmp/sync-gate/entry-go'])
                    observations=[];finished=None;blocked=None
                    for _ in range(10):
                        finished=gate_file(observer,'exit')
                        if finished:break
                        observed=c.state(c.worker);observations.append(observed)
                        if observed=='D':
                            raw=execute(f'cat /proc/{c.worker}/syscall').stdout.strip()
                            fields=raw.split();assert len(fields)==9 and fields[0]=='74' and int(fields[1],16)==selected['fd']
                            blocked=dict(state=observed,syscall=raw);break
                        time.sleep(.1)
                    assert finished or blocked,'neither actual sync exit nor blocked syscall was proved'
                    r['observed_states']=observations;r['blocked_sync']=blocked
                    r['exit_before_restore']=finished
                    r['outcome']='blocked_sync' if blocked else ('completed_while_nfsd_stopped' if down else 'healthy_completion')
                    if finished:assert finished['result']==0
                    began=time.monotonic();assert c.request('GET','/healthz')[0]==200
                    r['health_seconds']=time.monotonic()-began;assert r['health_seconds']<5
                    r['status_during']=c.request('GET','/api/v2/jobs/1')[1];assert r['status_during']==r['status_before']
                    assert c.children()==[c.worker]
                    r['epoch_during']=json.loads(execute('cat '+c.base+'/state/workers.json','1000:1000').stdout)
                    assert r['epoch_during']==r['epoch_before']
                    r['restore_started_ns']=clock()
                    if down:restore('nfsd');down=False
                    r['after_server']=state()
                    for _ in range(30):
                        finished=gate_file(observer,'exit')
                        if finished:break
                        time.sleep(.1)
                    else:raise AssertionError('selected fsync did not exit after restoration')
                    assert finished['result']==0;r['exit']=finished
                    r['custody_exit']=custody(c,phase);assert r['custody_exit']==r['custody_before']
                    r['original_request_before_release']=posted[1].read_text(encoding='utf-8')
                    assert not r['original_request_before_release'].startswith('HTTP/1.1 202')
                    if r['original_request_before_release'].startswith('HTTP/'):
                        code,body=c.parse(r['original_request_before_release']);assert code==503 and body['retryable'] and not body['source_paths_released']
                    r['exit_release_ns']=clock();run(['exec',observer,'touch','/tmp/sync-gate/exit-go'])
                    posted[0].wait(timeout=15);r['original_request']=dict(exit_code=posted[0].returncode,raw=posted[1].read_text(encoding='utf-8'))
                    if r['original_request']['raw'].startswith('HTTP/'):
                        code,body=c.parse(r['original_request']['raw']);r['original_request']['parsed']=[code,body]
                        assert code==202 or (code==503 and body['retryable'] and not body['source_paths_released'])
                    r['retry_responses']=[]
                    for _ in range(18):
                        code,handoff=c.request('POST','/api/v2/jobs',c.body);r['retry_responses'].append([code,handoff])
                        if code==202:break
                        assert code==503 and handoff['retryable'] and not handoff['source_paths_released'];time.sleep(1)
                    assert code==202 and handoff['job_id']=='1' and handoff['source_paths_released'];r['handoff']=handoff;r['handoff_ns']=clock()
                    assert execute('test ! -e '+original,'1000:1000',False).returncode==0;r['original_absent_at_202']=True
                    execute("printf 'next recording' >"+original,'1000:1000');r['source_reuse_ns']=clock()
                    committed=c.recover(restart=False);r['committed']=committed
                    assert c.service_pid()==r['coordinator_pid'] and committed['details']['files'][0]['attempt']==1 and not committed['details']['source_cleanup_enabled']
                    r['worker_exit']=c.await_exit(c.worker);r['trace']=finish_trace(run,observer);observer=None
                    c.verify();r['wire']=relay.command('stop_observe')
                    r['local_after']=execute(local,'1000:1000').stdout
                    r['enrollment_after']=execute(enrollment,'1000:1000').stdout
                    assert r['local_after']==r['local_before'] and r['enrollment_after']==r['enrollment_before']
                    r['private_after']=snapshot('/e/profile-source/'+c.label+'/source/.file-mover/1-0/data')
                    old=r['custody_before']['private'];parts=old['identity'].split(':')
                    assert r['private_after']==dict(identity=':'.join(parts[:2]+['1',parts[3]]),sha256=old['sha256'])
                    r['producer_after']=execute('cat '+original,'1000:1000').stdout;assert r['producer_after']=='next recording'
                    manifest_hash=execute('sha256sum '+c.destination+'/1/COMMITTED.json','1000:1000').stdout.split()[0]
                    assert json.loads(execute(c.binary+' --stop '+c.config_path,'1000:1000').stdout)['phase']=='Stopped'
                    assert c.service.wait(timeout=30)==0;c.worker=None;c.start(False)
                    code,replay=c.request('POST','/api/v2/jobs',c.body);r['replay']=replay
                    assert code==202 and replay['job_id']=='1' and replay['source_paths_released'] and c.request('GET','/api/v2/jobs/1')[1]['state']=='Committed'
                    assert execute('cat '+original,'1000:1000').stdout=='next recording'
                    assert execute('sha256sum '+c.destination+'/1/COMMITTED.json','1000:1000').stdout.split()[0]==manifest_hash
                    assert execute(local,'1000:1000').stdout==r['local_before'];c.verify()
                    assert json.loads(execute(c.binary+' --stop '+c.config_path,'1000:1000').stdout)['phase']=='Stopped'
                    assert c.service.wait(timeout=30)==0;r['original_state_preserved']=True;r['passed']=True
                    print('Claim fsync '+profile+' '+phase+' '+mode+': '+r['outcome'],flush=True)
                finally:
                    if down:restore('nfsd')
                    if observer:
                        run(['exec',observer,'touch','/tmp/sync-gate/entry-go','/tmp/sync-gate/exit-go'],False)
                    c.cleanup()
                    if 'wire' not in r:r['failed_wire']=relay.command('stop_observe')
                    if observer:r['incomplete_trace']=run(['logs',observer],False).stdout
