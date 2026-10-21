"""Four actual source-copy restart recoveries, following independent native controls."""
import hashlib
import json
import subprocess
import tarfile
import time
from nfs_runtime import run_runtime
from nfs_sync_support import start_trace, finish_trace


def qualify_mover(root,production_gate,qualification_gate,run,execute,client,server,
                  output,containers,config,relay,state,restore,snapshot,report):
    engine=['podman','--connection','podman-machine-default-root']
    current={p.relative_to(root/'rust').as_posix():p.read_bytes()
             for child in (root/'rust').iterdir() if child.name not in ('validation','target')
             for p in (child.rglob('*') if child.is_dir() else [child]) if p.is_file()}
    artifacts={};report['gates']={};report['mover_cases']=[]
    for mode,folder in (('production',production_gate),('qualification',qualification_gate)):
        gate=json.loads((folder/'report.json').read_text(encoding='utf-8'))
        assert gate['status']=='PASSED' and not gate.get('cleanup_error') and gate['config']==config
        assert gate['build_mode']==('production' if mode=='production' else 'nfs-qualification')
        assert hashlib.sha256((folder/'source.tar.gz').read_bytes()).hexdigest()==gate['source_sha256']
        with tarfile.open(folder/'source.tar.gz') as tar:
            assert {m.name:tar.extractfile(m).read() for m in tar if m.isfile()}==current,'stale gate'
        report['gates'][mode]=dict(run_id=gate['run_id'],source_sha256=gate['source_sha256'],artifacts={})
        for profile in ('debug','release'):
            item=next(a for a in gate['profiles'][profile]['artifacts'] if not a['test'])
            binary=folder/item['name'];assert hashlib.sha256(binary.read_bytes()).hexdigest()==item['sha256']
            report['gates'][mode]['artifacts'][profile]=item
            if mode=='qualification':
                remote='/tmp/qualification-'+profile
                run(['cp',str(binary),client+':'+remote]);execute('chmod 555 '+remote)
                artifacts['qualification-'+profile]=item['sha256']
    execute('mkdir /tmp/local; chmod 777 /tmp/local')
    stopped=None

    def adapted(script,user=None,check=True,target=None):
        assert target in (None,client)
        return execute(script,user,check)

    def spawn(script,name,target=None):
        assert target in (None,client)
        with (output/(name+'.log')).open('w',encoding='utf-8') as log:
            return subprocess.Popen(engine+['exec','--user','1000:1000','--env','LD_BIND_NOW=1',client,
                                           '/bin/sh','-eu','-c',script],stdout=log,stderr=log)

    def resume():
        nonlocal stopped
        if stopped:
            restore(stopped);stopped=None

    def clock():
        return int(run(['exec',relay.container,'python3','-c','import time; print(time.monotonic_ns())']).stdout)

    def unpublished(c):
        parent='/e/profile-destination/'+c.label+'/destination/1'
        result=run(['exec','--user','1000:1000',report['storage_reader'],'/bin/sh','-eu','-c',
                    'test -d '+parent+'; test ! -e '+parent+'/nested/data.bin; test ! -e '+parent+
                    '/COMMITTED.json; printf absent']).stdout
        assert result=='absent'
        return dict(final_absent=True,manifest_absent=True,observation='independent read-only backing filesystem')

    def cases(Case):
        nonlocal stopped
        for profile in ('debug','release'):
            for kind in ('nfsd','container'):
                print('Mover server recovery '+profile+' '+kind,flush=True)
                verification=report.get('verification_recovery',False)
                c=Case(profile,'verify_read' if verification else 'source_copy',suffix='-server-'+kind,both_nfs=True)
                r=c.result;report['mover_cases'].append(r);report['rust_executed']=True
                distinct=report.get('distinct_filesystems',False)
                r.update(kind=kind,scenario_id='SC-123' if verification else 'SC-122' if distinct else 'SC-121',layout='two distinct retained tmpfs/client NFS filesystems, one server, local state' if distinct else 'two buffered NFS exports, one persistent backing volume/server, local state',config=c.config)
                observer=None
                try:
                    original=c.source+'/current/nested/data.bin';private=c.source+'/.file-mover/1-0/data'
                    r['original_source']=execute("stat -c '%d:%i:%s' "+original+'; sha256sum '+original,'1000:1000').stdout.splitlines()
                    local_command="stat -c '%d:%i' "+c.base+'/state/jobs.sqlite; sha256sum '+c.config_path
                    enrollment_command='sha256sum '+c.source+'/.file-mover/source-enrollment.json'
                    r['original_local_state']=execute(local_command,'1000:1000').stdout
                    r['original_enrollment']=execute(enrollment_command,'1000:1000').stdout
                    relay.command('observe')
                    c.start(True)
                    code,handoff=c.request('POST','/api/v2/jobs',c.body)
                    assert code==202 and handoff['source_paths_released'] and handoff['job_id']=='1'
                    r['handoff']=handoff
                    c.await_pause();r['coordinator_pid']=c.service_pid();r['worker_pid']=c.worker
                    execute("printf 'next recording' >"+original,'1000:1000')
                    r['status_before']=c.request('GET','/api/v2/jobs/1')[1]
                    assert r['status_before']['state']=='Claimed' and r['status_before']['details']['files'][0]['transfer_phase']==('Copied' if verification else 'Intent')
                    stage=c.destination+'/1/.staging/1.part'
                    r['staging_before']=execute("stat -c '%d:%i:%s' "+stage,'1000:1000').stdout.strip()
                    assert r['staging_before'].split(':')[-1]==('2097169' if verification else '1048576')
                    if distinct:
                        assert r['original_source'][0].split(':')[0]!=r['staging_before'].split(':')[0]
                        assert r['original_local_state'].splitlines()[0].split(':')[0] not in (r['original_source'][0].split(':')[0],r['staging_before'].split(':')[0])
                    r['epoch_before']=json.loads(execute('cat '+c.base+'/state/workers.json','1000:1000').stdout)
                    assert r['epoch_before']['group']==int(r['coordinator_pid'])
                    backing='/e/profile-source/'+c.label+'/source/.file-mover/1-0/data'
                    r['source_backing_before']=snapshot(backing)
                    assert r['source_backing_before']['sha256']==r['original_source'][1].split()[0]
                    if verification:
                        stage_backing='/e/profile-destination/'+c.label+'/destination/1/.staging/1.part'
                        r['destination_backing_before']=snapshot(stage_backing)
                        assert r['destination_backing_before']['sha256']==r['source_backing_before']['sha256']
                        r['publication_before']=unpublished(c)
                    observer=start_trace(run,client,c.worker,containers,config,expected_exit='supervised-delivery',io=verification)
                    r['clock_namespaces']={actor:run(['exec',actor,'readlink','/proc/self/ns/time']).stdout.strip()
                                           for actor in (client,observer,relay.container)}
                    assert len(set(r['clock_namespaces'].values()))==1
                    r['before_server']=state();r['before_wire']=relay.command('checkpoint')
                    stopped=kind
                    if kind=='nfsd':
                        run(['exec',server,'rpc.nfsd','0']);r['stopped_server']=state()
                        assert r['stopped_server']['threads']=='0'
                    else:
                        run(['exec',server,'rpc.nfsd','0'])
                        r['quiesced_server']=state();assert r['quiesced_server']['threads']=='0'
                        run(['kill','--signal','KILL',server]);r['stop_exit_code']=int(run(['wait',server]).stdout.strip())
                        r['stopped_container']=json.loads(run(['inspect',server]).stdout)[0]['State']
                        assert r['stop_exit_code']==137 and r['stopped_container']['Status']=='exited'
                        assert not r['stopped_container']['Running'] and r['stopped_container']['Pid']==0
                    r['source_backing_stopped']=snapshot(backing)
                    assert r['source_backing_stopped']==r['source_backing_before']
                    if verification:
                        r['destination_backing_stopped']=snapshot(stage_backing)
                        assert r['destination_backing_stopped']==r['destination_backing_before']
                        r['publication_during']=unpublished(c)
                    execute(': >'+c.rendezvous+'/go','1000:1000')
                    for _ in range(50):
                        if c.state(c.worker)=='D':break
                        assert c.service.poll() is None;time.sleep(.1)
                    else:raise AssertionError('no actual blocked payload reader')
                    raw=execute(f'cat /proc/{c.worker}/syscall').stdout.strip();fields=raw.split()
                    assert len(fields)==9 and fields[0]=='0' and int(fields[3],16)==1048576,raw
                    fd=int(fields[1],16);path=execute(f'readlink /proc/{c.worker}/fd/{fd}').stdout.strip()
                    assert path==(stage if verification else private) and c.children()==[c.worker]
                    execute('test ! -e '+c.rendezvous+'/read-completed','1000:1000')
                    r['blocked_read']=dict(state=c.state(c.worker),syscall=raw,fd=fd,path=path,read_completed=False,fdinfo=execute(f'cat /proc/{c.worker}/fdinfo/{fd}').stdout)
                    assert r['blocked_read']['state']=='D'
                    r['worker_security']=execute(f'cat /proc/{c.worker}/status').stdout
                    began=time.monotonic();assert c.request('GET','/healthz')[0]==200
                    r['health_seconds']=time.monotonic()-began;assert r['health_seconds']<5
                    r['status_during']=c.request('GET','/api/v2/jobs/1')[1];assert r['status_during']==r['status_before']
                    r['local_state_during']=execute(local_command,'1000:1000').stdout
                    assert r['local_state_during']==r['original_local_state']
                    r['guard_exit']=execute('flock -n -E 73 '+c.base+'/state/instance.lock true','1000:1000',False).returncode
                    assert r['guard_exit']==73
                    contender_config=output/(c.label+'-contender.json')
                    contender_config.write_text(json.dumps(dict(c.config,bind='127.0.0.1:0')),encoding='utf-8')
                    remote_contender=c.base+'/contender.json'
                    run(['cp',str(contender_config),client+':'+remote_contender])
                    began=time.monotonic()
                    contender=execute(c.binary+' '+remote_contender,'1000:1000',False)
                    r['contender']=dict(exit_code=contender.returncode,stderr=contender.stderr)
                    r['contender']['seconds']=time.monotonic()-began
                    r['contender']['config']=json.loads(contender_config.read_text(encoding='utf-8'))
                    assert r['contender']['seconds']<6
                    assert contender.returncode!=0 and 'local instance or surviving worker already owns state' in contender.stderr
                    assert c.children()==[c.worker] and c.state(c.worker)=='D'
                    r['epoch_during']=json.loads(execute('cat '+c.base+'/state/workers.json','1000:1000').stdout)
                    assert r['epoch_during']==r['epoch_before']
                    r['restore_started_ns']=clock();resume();r['after_server']=state()
                    committed=c.recover(restart=False);r['committed']=committed
                    assert c.service_pid()==r['coordinator_pid'] and c.service.poll() is None
                    r['coordinator_after']=c.service_pid()
                    assert committed['details']['files'][0]['attempt']==1 and not committed['details']['source_cleanup_enabled']
                    r['worker_exit']=c.await_exit(c.worker)
                    r['trace']=finish_trace(run,observer);observer=None
                    assert r['trace']['pid']==int(r['worker_pid'])
                    execute('test -f '+c.rendezvous+'/read-completed','1000:1000')
                    c.verify()
                    r['source_backing_after']=snapshot(backing);assert r['source_backing_after']==r['source_backing_before']
                    r['final_identity']=execute("stat -c '%d:%i' "+c.destination+'/1/nested/data.bin','1000:1000').stdout.strip()
                    assert r['final_identity']==':'.join(r['staging_before'].split(':')[:2])
                    if verification:
                        r['destination_backing_after']=snapshot('/e/profile-destination/'+c.label+'/destination/1/nested/data.bin')
                        assert r['destination_backing_after']==r['destination_backing_before']
                    r['local_state_after']=execute(local_command,'1000:1000').stdout
                    r['enrollment_after']=execute(enrollment_command,'1000:1000').stdout
                    assert r['local_state_after']==r['original_local_state']
                    assert r['enrollment_after']==r['original_enrollment']
                    r['wire']=relay.command('stop_observe')
                    manifest_hash=execute('sha256sum '+c.destination+'/1/COMMITTED.json','1000:1000').stdout.split()[0]
                    stopped_reply=json.loads(execute(c.binary+' --stop '+c.config_path,'1000:1000').stdout)
                    assert stopped_reply['phase']=='Stopped' and c.service.wait(timeout=30)==0
                    c.worker=None;c.start(False)
                    code,replay=c.request('POST','/api/v2/jobs',c.body)
                    assert code==202 and replay['job_id']=='1' and replay['source_paths_released']
                    assert c.request('GET','/api/v2/jobs/1')[1]['state']=='Committed'
                    assert execute('cat '+original,'1000:1000').stdout=='next recording'
                    assert execute('sha256sum '+c.destination+'/1/COMMITTED.json','1000:1000').stdout.split()[0]==manifest_hash
                    assert execute(local_command,'1000:1000').stdout==r['original_local_state']
                    c.verify();r['replay']=replay;r['original_state_preserved']=True
                    assert json.loads(execute(c.binary+' --stop '+c.config_path,'1000:1000').stdout)['phase']=='Stopped'
                    assert c.service.wait(timeout=30)==0
                    r['passed']=True;print('Mover server recovery '+profile+' '+kind+': PASS',flush=True)
                finally:
                    resume();c.cleanup()
                    if 'wire' not in r:r['failed_wire']=relay.command('stop_observe')
                    if observer:r['incomplete_trace']=run(['logs',observer],False).stdout
    run_runtime(run,adapted,spawn,resume,server,output,client,artifacts,report,
                case_runner=cases,nfs_root='/tmp/recovery-source',destination_nfs_root='/tmp/recovery-destination')
    assert len(report['mover_cases'])==4 and all(c['passed'] for c in report['mover_cases'])
