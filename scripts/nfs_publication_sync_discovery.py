"""Exact actual-worker publication fsync entry/exit capability controls."""
import json
import time
from nfs_sync_support import start_trace, finish_trace


def qualify(Case,run,execute,client,server,output,containers,config,relay,state,restore,snapshot,report):
    def clock():
        return int(run(['exec',relay.container,'python3','-c','import time; print(time.monotonic_ns())']).stdout)

    def custody(c,phase):
        area='/e/profile-destination/'+c.label+'/destination/1'
        source='/e/profile-source/'+c.label+'/source/.file-mover/1-0/data'
        paths=[source,area+'/.staging/'+('1.part' if phase=='payload' else 'COMMITTED.part'),
               area+('/nested/data.bin' if phase=='payload' else '/COMMITTED.json')]
        if phase=='manifest':paths.append(area+'/nested/data.bin')
        guard='test ! -e '+area+('/COMMITTED.json' if phase=='payload' else '/.staging/1.part')+'; '
        script=guard+"stat -c '%d:%i:%h:%s' "+' '.join(paths)+'; sha256sum '+' '.join(paths)
        if phase=='manifest':script+='; cat '+paths[1]
        lines=run(['exec','--user','1000:1000',report['storage_reader'],'/bin/sh','-eu','-c',script]).stdout.splitlines()
        n=len(paths);assert len(lines)>=2*n
        rows={name:dict(identity=lines[i],sha256=lines[n+i].split()[0]) for i,name in enumerate(('source','staging','final','payload')[:n])}
        assert rows['staging']==rows['final'] and rows['staging']['identity'].split(':')[2]=='2'
        if phase=='payload':assert rows['source']['sha256']==rows['final']['sha256']
        else:
            rows['manifest_bytes']='\n'.join(lines[2*n:])
            assert rows['source']['sha256']==rows['payload']['sha256'] and rows['payload']['identity'].split(':')[2]=='1'
        rows['absent']='manifest' if phase=='payload' else 'payload_staging'
        return rows

    def gate_file(observer,name):
        value=run(['exec',observer,'cat','/tmp/sync-gate/'+name+'.json'],False)
        return json.loads(value.stdout) if value.returncode==0 else None

    for profile in ('debug','release'):
        for phase in ('payload','manifest'):
            for mode in ('healthy','nfsd-stopped'):
                print('Publication fsync '+profile+' '+phase+' '+mode,flush=True)
                point='file_link_rpc' if phase=='payload' else 'manifest_link_rpc'
                c=Case(profile,point,suffix='-sync-'+mode,both_nfs=True)
                r=c.result;report['mover_cases'].append(r);report['rust_executed']=True
                r.update(scenario_id='SC-128',phase=phase,mode=mode,config=c.config,
                         layout='two distinct retained tmpfs/client NFS filesystems, local state')
                observer=None;down=False
                try:
                    original=c.source+'/current/nested/data.bin'
                    local="stat -c '%d:%i' "+c.base+'/state/jobs.sqlite; sha256sum '+c.config_path
                    enrollment='sha256sum '+c.source+'/.file-mover/source-enrollment.json'
                    r['local_before']=execute(local,'1000:1000').stdout
                    r['enrollment_before']=execute(enrollment,'1000:1000').stdout
                    relay.command('observe');c.start(True)
                    code,handoff=c.request('POST','/api/v2/jobs',c.body)
                    assert code==202 and handoff['job_id']=='1' and handoff['source_paths_released'];r['handoff']=handoff
                    c.await_pause();r['coordinator_pid']=c.service_pid();r['worker_pid']=c.worker
                    execute("printf 'next recording' >"+original,'1000:1000')
                    target=c.destination+'/1/'+('nested/data.bin' if phase=='payload' else 'COMMITTED.json')
                    observer=start_trace(run,client,c.worker,containers,config,expected_exit='supervised-delivery',io=True,gate=dict(path=target))
                    r['clock_namespaces']={x:run(['exec',x,'readlink','/proc/self/ns/time']).stdout.strip() for x in (client,observer,relay.container)}
                    assert len(set(r['clock_namespaces'].values()))==1
                    execute(': >'+c.rendezvous+'/go','1000:1000')
                    for _ in range(25):
                        selected=gate_file(observer,'entry')
                        if selected:break
                        assert c.service.poll() is None;time.sleep(.1)
                    else:raise AssertionError('publication fsync entry not intercepted')
                    r['entry']=selected;assert selected['syscall']==74 and selected['descriptor']['path']==target
                    r['entry_worker_state']=c.state(c.worker);assert r['entry_worker_state'] in ('t','T')
                    r['status_before']=c.request('GET','/api/v2/jobs/1')[1]
                    assert r['status_before']['state']=='Claimed'
                    assert r['status_before']['details']['files'][0]['transfer_phase']==('PublishIntent' if phase=='payload' else 'Published')
                    if phase=='manifest':assert r['status_before']['details']['manifest_phase']==3
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
                    r['exit_release_ns']=clock();run(['exec',observer,'touch','/tmp/sync-gate/exit-go'])
                    committed=c.recover(restart=False);r['committed']=committed
                    assert c.service_pid()==r['coordinator_pid'] and committed['details']['files'][0]['attempt']==1 and not committed['details']['source_cleanup_enabled']
                    r['worker_exit']=c.await_exit(c.worker);r['trace']=finish_trace(run,observer);observer=None
                    c.verify();r['wire']=relay.command('stop_observe')
                    r['local_after']=execute(local,'1000:1000').stdout
                    r['enrollment_after']=execute(enrollment,'1000:1000').stdout
                    assert r['local_after']==r['local_before'] and r['enrollment_after']==r['enrollment_before']
                    final='/e/profile-destination/'+c.label+'/destination/1/'+('nested/data.bin' if phase=='payload' else 'COMMITTED.json')
                    r['final_after']=snapshot(final);old=r['custody_before']['final'];parts=old['identity'].split(':')
                    assert r['final_after']==dict(identity=':'.join(parts[:2]+['1',parts[3]]),sha256=old['sha256'])
                    r['staging_absent']=execute('test ! -e '+c.destination+'/1/.staging/'+('1.part' if phase=='payload' else 'COMMITTED.part'),'1000:1000',False).returncode==0
                    assert r['staging_absent']
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
                    print('Publication fsync '+profile+' '+phase+' '+mode+': '+r['outcome'],flush=True)
                finally:
                    if down:restore('nfsd')
                    if observer:
                        run(['exec',observer,'touch','/tmp/sync-gate/entry-go','/tmp/sync-gate/exit-go'],False)
                    c.cleanup()
                    if 'wire' not in r:r['failed_wire']=relay.command('stop_observe')
                    if observer:r['incomplete_trace']=run(['logs',observer],False).stdout
