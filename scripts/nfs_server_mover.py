"""Selected actual mover restart recoveries, following independent native controls."""
import base64
import hashlib
import json
import sqlite3
import subprocess
import tarfile
import time
import zlib
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

    def aliases(c):
        parent='/e/profile-destination/'+c.label+'/destination/1'
        result=run(['exec','--user','1000:1000',report['storage_reader'],'/bin/sh','-eu','-c',
                    'test -d '+parent+'; test ! -e '+parent+'/COMMITTED.json; '+
                    "stat -c '%d:%i:%h:%s' "+parent+'/.staging/1.part '+parent+'/nested/data.bin; '+
                    'sha256sum '+parent+'/.staging/1.part '+parent+'/nested/data.bin']).stdout.splitlines()
        assert len(result)==4 and result[0]==result[1] and result[0].split(':')[-2:]==['2','2097169']
        assert result[2].split()[0]==result[3].split()[0]
        return dict(staging=dict(identity=result[0],sha256=result[2].split()[0]),
                    final=dict(identity=result[1],sha256=result[3].split()[0]),manifest_absent=True)

    def manifest_aliases(c):
        parent='/e/profile-destination/'+c.label+'/destination/1'
        result=run(['exec','--user','1000:1000',report['storage_reader'],'/bin/sh','-eu','-c',
                    'test ! -e '+parent+'/.staging/1.part; '+
                    "stat -c '%d:%i:%h:%s' "+parent+'/.staging/COMMITTED.part '+parent+'/COMMITTED.json; '+
                    'sha256sum '+parent+'/.staging/COMMITTED.part '+parent+'/COMMITTED.json; cat '+parent+'/COMMITTED.json']).stdout.splitlines()
        assert len(result)>=5 and result[0]==result[1] and result[0].split(':')[2]=='2'
        assert result[2].split()[0]==result[3].split()[0]
        raw='\n'.join(result[4:])
        assert hashlib.sha256(raw.encode()).hexdigest()==result[2].split()[0]
        return dict(staging=dict(identity=result[0],sha256=result[2].split()[0]),
                    final=dict(identity=result[1],sha256=result[3].split()[0]),
                    bytes=raw,payload_staging_absent=True)

    def manifest_staging(c):
        parent='/e/profile-destination/'+c.label+'/destination/1'
        result=run(['exec','--user','1000:1000',report['storage_reader'],'/bin/sh','-eu','-c',
                    'test ! -e '+parent+'/COMMITTED.json; test ! -e '+parent+'/.staging/1.part; '+
                    "stat -c '%d:%i:%h:%s' "+parent+'/.staging/COMMITTED.part; '+
                    'sha256sum '+parent+'/.staging/COMMITTED.part; cat '+parent+'/.staging/COMMITTED.part']).stdout.splitlines()
        assert len(result)>=3 and result[0].split(':')[2]=='1'
        raw='\n'.join(result[2:]);assert hashlib.sha256(raw.encode()).hexdigest()==result[1].split()[0]
        return dict(identity=result[0],sha256=result[1].split()[0],bytes=raw,manifest_absent=True,payload_staging_absent=True)

    def frozen_local_database(c,tag):
        # Coordinator has exited; workers never write SQLite. Inspect copies only.
        folder=output/(c.label+'-'+tag);folder.mkdir()
        files={}
        for name in ('jobs.sqlite','jobs.sqlite-wal'):
            remote=c.base+'/state/'+name
            if execute('test -f '+remote,'1000:1000',False).returncode:
                assert name!='jobs.sqlite';continue
            before=execute('sha256sum '+remote,'1000:1000').stdout.split()[0]
            local=folder/name;run(['cp',client+':'+remote,str(local)])
            data=local.read_bytes();after=execute('sha256sum '+remote,'1000:1000').stdout.split()[0]
            assert before==after==hashlib.sha256(data).hexdigest()
            files[name]=dict(sha256=before,zlib_base64=base64.b64encode(zlib.compress(data,9)).decode())
        with sqlite3.connect((folder/'jobs.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as db:
            db.execute('PRAGMA query_only=ON')
            manifest=db.execute('SELECT phase,bytes,sha256 FROM manifests WHERE job_id=1').fetchone()
            transfers=db.execute('SELECT file_index,attempt,phase FROM transfers WHERE job_id=1 ORDER BY file_index,attempt').fetchall()
        assert manifest[0]==3 and manifest[1]==c.result['manifest_staging_before']['bytes'] and manifest[2]==c.result['manifest_staging_before']['sha256']
        assert transfers==[(0,1,4)]
        return dict(files=files,manifest=list(manifest),transfers=[list(row) for row in transfers],observation='copied local database and existing WAL; no original SQLite opened')

    def cases(Case):
        nonlocal stopped
        if report.get('publication_sync_discovery'):
            from nfs_publication_sync_discovery import qualify
            return qualify(Case,run,execute,client,server,output,containers,config,relay,state,restore,snapshot,report)

        for profile in ('debug','release'):
            for kind in ('nfsd','container'):
                print('Mover server recovery '+profile+' '+kind,flush=True)
                verification=report.get('verification_recovery',False)
                publication=report.get('publication_recovery',False)
                manifest=report.get('manifest_recovery',False)
                payload_link=report.get('payload_link_recovery',False)
                manifest_death=report.get('manifest_link_death_recovery',False)
                death=report.get('payload_link_death_recovery',False) or manifest_death
                manifest_link=report.get('manifest_link_recovery',False)
                c=Case(profile,'manifest_link_rpc' if manifest_link else 'file_link_rpc' if payload_link else 'manifest_unlink' if manifest else 'file_unlink' if publication else 'verify_read' if verification else 'source_copy',suffix='-server-'+kind,both_nfs=True)
                r=c.result;report['mover_cases'].append(r);report['rust_executed']=True
                distinct=report.get('distinct_filesystems',False)
                r.update(kind=kind,scenario_id='SC-130' if manifest_death else 'SC-129' if death else 'SC-127' if manifest_link else 'SC-126' if payload_link else 'SC-125' if manifest else 'SC-124' if publication else 'SC-123' if verification else 'SC-122' if distinct else 'SC-121',layout='two distinct retained tmpfs/client NFS filesystems, one server, local state' if distinct else 'two buffered NFS exports, one persistent backing volume/server, local state',config=c.config)
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
                    assert r['status_before']['state']=='Claimed' and r['status_before']['details']['files'][0]['transfer_phase']==('Published' if manifest or manifest_link else 'PublishIntent' if publication or payload_link else 'Copied' if verification else 'Intent')
                    if manifest or manifest_link:assert r['status_before']['details']['manifest_phase']==3
                    stage=c.destination+'/1/.staging/1.part'
                    # For manifest cases the payload has already left staging; retain its final identity.
                    r['staging_before']=execute("stat -c '%d:%i:%s' "+(c.destination+'/1/nested/data.bin' if manifest or manifest_link else stage),'1000:1000').stdout.strip()
                    assert r['staging_before'].split(':')[-1]==('2097169' if verification or publication or manifest or payload_link or manifest_link else '1048576')
                    if distinct:
                        assert r['original_source'][0].split(':')[0]!=r['staging_before'].split(':')[0]
                        assert r['original_local_state'].splitlines()[0].split(':')[0] not in (r['original_source'][0].split(':')[0],r['staging_before'].split(':')[0])
                    r['epoch_before']=json.loads(execute('cat '+c.base+'/state/workers.json','1000:1000').stdout)
                    assert r['epoch_before']['group']==int(r['coordinator_pid'])
                    backing='/e/profile-source/'+c.label+'/source/.file-mover/1-0/data'
                    r['source_backing_before']=snapshot(backing)
                    assert r['source_backing_before']['sha256']==r['original_source'][1].split()[0]
                    if verification or payload_link:
                        stage_backing='/e/profile-destination/'+c.label+'/destination/1/.staging/1.part'
                        r['destination_backing_before']=snapshot(stage_backing)
                        assert r['destination_backing_before']['sha256']==r['source_backing_before']['sha256']
                        if payload_link:assert r['destination_backing_before']['identity'].split(':')[2:]==['1','2097169']
                        r['publication_before']=unpublished(c)
                    if publication:
                        r['aliases_before']=aliases(c)
                        assert r['aliases_before']['staging']['sha256']==r['source_backing_before']['sha256']
                    if manifest:
                        r['aliases_before']=manifest_aliases(c)
                        r['payload_before']=snapshot('/e/profile-destination/'+c.label+'/destination/1/nested/data.bin')
                        assert r['payload_before']['sha256']==r['source_backing_before']['sha256'] and r['payload_before']['identity'].split(':')[2]=='1'
                    if manifest_link:
                        r['manifest_staging_before']=manifest_staging(c)
                        r['payload_before']=snapshot('/e/profile-destination/'+c.label+'/destination/1/nested/data.bin')
                        assert r['payload_before']['sha256']==r['source_backing_before']['sha256'] and r['payload_before']['identity'].split(':')[2]=='1'
                        if manifest_death:
                            stage_backing='/e/profile-destination/'+c.label+'/destination/1/.staging/COMMITTED.part'
                            before=r['manifest_staging_before']
                            r['destination_backing_before']=dict(identity=before['identity'],sha256=before['sha256'])
                    observer=start_trace(run,client,c.worker,containers,config,expected_exit='coordinator-death' if death else 'supervised-delivery',io=verification or publication or manifest or payload_link or manifest_link)
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
                    if verification or payload_link:
                        r['destination_backing_stopped']=snapshot(stage_backing)
                        assert r['destination_backing_stopped']==r['destination_backing_before']
                        r['publication_during']=unpublished(c)
                    if publication:
                        r['aliases_stopped']=aliases(c)
                        assert r['aliases_stopped']==r['aliases_before']
                    if manifest:
                        r['aliases_stopped']=manifest_aliases(c)
                        r['payload_stopped']=snapshot('/e/profile-destination/'+c.label+'/destination/1/nested/data.bin')
                        assert r['aliases_stopped']==r['aliases_before'] and r['payload_stopped']==r['payload_before']
                    if manifest_link:
                        r['manifest_staging_stopped']=manifest_staging(c)
                        r['payload_stopped']=snapshot('/e/profile-destination/'+c.label+'/destination/1/nested/data.bin')
                        assert r['manifest_staging_stopped']==r['manifest_staging_before'] and r['payload_stopped']==r['payload_before']
                        if manifest_death:r['destination_backing_stopped']=snapshot(stage_backing)
                    execute(': >'+c.rendezvous+'/go','1000:1000')
                    for _ in range(50):
                        if c.state(c.worker)=='D':break
                        assert c.service.poll() is None;time.sleep(.1)
                    else:raise AssertionError('no actual blocked payload reader')
                    if payload_link or manifest_link:
                        raw=execute(f'cat /proc/{c.worker}/syscall').stdout.strip();fields=raw.split()
                        assert len(fields)==9 and fields[0]=='265' and int(fields[5],16)==0,raw
                        fd=int(fields[1],16);newfd=int(fields[3],16)
                        paths=execute(f'readlink /proc/{c.worker}/fd/{fd}; readlink /proc/{c.worker}/fd/{newfd}').stdout.splitlines()
                        assert paths==[c.destination+'/1/.staging',c.destination+('/1' if manifest_link else '/1/nested')] and c.children()==[c.worker]
                        r['blocked_link']=dict(state=c.state(c.worker),syscall=raw,fd=fd,path=paths[0],newfd=newfd,newpath=paths[1],
                            fdinfo=execute(f'cat /proc/{c.worker}/fdinfo/{fd}').stdout,
                            newfdinfo=execute(f'cat /proc/{c.worker}/fdinfo/{newfd}').stdout)
                        assert r['blocked_link']['state']=='D'
                    elif publication or manifest:
                        raw=execute(f'cat /proc/{c.worker}/syscall').stdout.strip();fields=raw.split()
                        assert len(fields)==9 and fields[0]=='263',raw
                        fd=int(fields[1],16);path=execute(f'readlink /proc/{c.worker}/fd/{fd}').stdout.strip()
                        assert path==c.destination+'/1/.staging' and c.children()==[c.worker]
                        r['blocked_unlink']=dict(state=c.state(c.worker),syscall=raw,fd=fd,path=path,
                            fdinfo=execute(f'cat /proc/{c.worker}/fdinfo/{fd}').stdout)
                        assert r['blocked_unlink']['state']=='D'
                    else:
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
                    if death:
                        # Kill the coordinator only; never its group or a replacement.
                        r['coordinator_kill_ns']=clock();c.signal(r['coordinator_pid'],'KILL')
                        r['coordinator_exit_code']=c.service.wait(timeout=10)
                        assert r['coordinator_exit_code']!=0 and c.state(r['coordinator_pid']) in ('','Z')
                        r['orphan_samples']=[]
                        for _ in range(3):
                            sample=dict(worker_state=c.state(c.worker))
                            sample['guard_exit']=execute('flock -n -E 73 '+c.base+'/state/instance.lock true','1000:1000',False).returncode
                            status=execute(c.binary+' --status '+c.config_path,'1000:1000',False)
                            sample['status_exit']=status.returncode;sample['status']=json.loads(status.stdout)
                            sample['worker_after']=c.state(c.worker)
                            assert sample['worker_state']==sample['worker_after']=='D'
                            assert sample['guard_exit'] in (0,73) and sample['status_exit']==2 and sample['status']['phase']=='OwnerUnavailable'
                            r['orphan_samples'].append(sample)
                        r['orphan_contenders']=[]
                        for command,tail in (('', ''),('--initialize-source ',''),('--transfer-one ',' 1')):
                            began=time.monotonic();reply=execute(c.binary+' '+command+remote_contender+tail,'1000:1000',False)
                            item=dict(command=command.strip() or 'service',exit_code=reply.returncode,stderr=reply.stderr,seconds=time.monotonic()-began)
                            assert item['seconds']<6 and item['exit_code']!=0 and 'local instance or surviving worker already owns state' in item['stderr']
                            assert c.state(c.worker)=='D';r['orphan_contenders'].append(item)
                        r['orphan_epoch']=json.loads(execute('cat '+c.base+'/state/workers.json','1000:1000').stdout)
                        assert r['orphan_epoch']==r['epoch_before']
                        r['orphan_source']=snapshot(backing);r['orphan_staging']=snapshot(stage_backing);r['orphan_publication']=manifest_staging(c) if manifest_death else unpublished(c)
                        if manifest_death:
                            r['orphan_payload']=snapshot('/e/profile-destination/'+c.label+'/destination/1/nested/data.bin')
                            assert r['orphan_payload']==r['payload_before'] and r['orphan_publication']==r['manifest_staging_before']
                        assert r['orphan_source']==r['source_backing_before'] and r['orphan_staging']==r['destination_backing_before']
                    if manifest_death:r['database_before_restore']=frozen_local_database(c,'before-restore')
                    r['restore_started_ns']=clock();resume();r['after_server']=state()
                    if death:
                        r['worker_exit']=c.await_exit(c.worker);r['worker_exit_observed_ns']=clock()
                        r['trace']=finish_trace(run,observer);observer=None;c.worker=None
                        # Independently observe the remote namespace after restoration and actual exit.
                        r['settlement_source']=snapshot(backing)
                        def optional_snapshot(path):
                            lines=run(['exec','--user','1000:1000',report['storage_reader'],'/bin/sh','-eu','-c',
                                'if test -e '+path+'; then stat -c %d:%i:%h:%s '+path+'; sha256sum '+path+'; fi']).stdout.splitlines()
                            return dict(identity=lines[0],sha256=lines[1].split()[0]) if lines else None
                        r['settlement_stage']=optional_snapshot(stage_backing)
                        parent='/e/profile-destination/'+c.label+'/destination/1'
                        r['settlement_final']=optional_snapshot(parent+('/COMMITTED.json' if manifest_death else '/nested/data.bin'))
                        if manifest_death:
                            r['settlement_manifest_absent']=r['settlement_final'] is None
                            r['settlement_payload']=snapshot(parent+'/nested/data.bin')
                            assert r['settlement_payload']==r['payload_before']
                            run(['exec','--user','1000:1000',report['storage_reader'],'test','!','-e',parent+'/.staging/1.part'])
                            r['settlement_payload_staging_absent']=True
                            if r['settlement_final']:
                                r['settlement_manifest_bytes']=run(['exec','--user','1000:1000',report['storage_reader'],'cat',parent+'/COMMITTED.json']).stdout
                                assert r['settlement_manifest_bytes']==r['manifest_staging_before']['bytes']
                        else:
                            run(['exec','--user','1000:1000',report['storage_reader'],'test','!','-e',parent+'/COMMITTED.json'])
                            r['settlement_manifest_absent']=True
                        assert r['settlement_source']==r['source_backing_before']
                        stage_observed,final_observed=r['settlement_stage'],r['settlement_final']
                        assert stage_observed or final_observed
                        expected=r['destination_backing_before'];expected_size=expected['identity'].split(':')[3]
                        for observed in (stage_observed,final_observed):
                            if observed:
                                assert observed['sha256']==expected['sha256']
                                assert observed['identity'].split(':')[:2]==expected['identity'].split(':')[:2]
                                assert observed['identity'].split(':')[2:]==(['2',expected_size] if stage_observed and final_observed else ['1',expected_size])
                        if stage_observed and final_observed:assert stage_observed==final_observed
                        if manifest_death:
                            r['database_after_exit']=frozen_local_database(c,'after-exit')
                            assert r['database_after_exit']==r['database_before_restore']
                        r['status_after_exit']=json.loads(execute(c.binary+' --status '+c.config_path,'1000:1000',False).stdout)
                        assert r['status_after_exit']['phase']=='NoActiveOwner'
                        r['restart_started_ns']=clock();committed=c.recover();r['committed']=committed
                        r['replacement_epoch']=json.loads(execute('cat '+c.base+'/state/workers.json','1000:1000').stdout)
                        assert r['replacement_epoch']['group']==int(c.service_pid())!=r['epoch_before']['group']
                        assert all(r['replacement_epoch'][k]==r['epoch_before'][k] for k in ('version','boot','namespace','guard'))
                    else:
                        committed=c.recover(restart=False);r['committed']=committed
                        assert c.service_pid()==r['coordinator_pid'] and c.service.poll() is None
                        r['worker_exit']=c.await_exit(c.worker)
                        r['trace']=finish_trace(run,observer);observer=None
                    r['coordinator_after']=c.service_pid()
                    assert committed['details']['files'][0]['attempt']==1 and not committed['details']['source_cleanup_enabled']
                    assert r['trace']['pid']==int(r['worker_pid'])
                    if not (publication or manifest or payload_link or manifest_link):execute('test -f '+c.rendezvous+'/read-completed','1000:1000')
                    c.verify()
                    r['source_backing_after']=snapshot(backing);assert r['source_backing_after']==r['source_backing_before']
                    r['final_identity']=execute("stat -c '%d:%i' "+c.destination+'/1/nested/data.bin','1000:1000').stdout.strip()
                    assert r['final_identity']==':'.join(r['staging_before'].split(':')[:2])
                    if payload_link:
                        r['staging_absent_after']=execute('test ! -e '+stage,'1000:1000',False).returncode==0
                        assert r['staging_absent_after']
                    if verification or payload_link:
                        r['destination_backing_after']=snapshot('/e/profile-destination/'+c.label+'/destination/1/nested/data.bin')
                        assert r['destination_backing_after']==r['destination_backing_before']
                    if publication:
                        r['final_backing_after']=snapshot('/e/profile-destination/'+c.label+'/destination/1/nested/data.bin')
                        expected=r['aliases_before']['final'];old=expected['identity'].split(':')
                        assert r['final_backing_after']==dict(identity=':'.join(old[:2]+['1',old[3]]),sha256=expected['sha256'])
                        r['staging_absent_after']=execute('test ! -e '+stage,'1000:1000',False).returncode==0
                        assert r['staging_absent_after']
                    if manifest:
                        r['final_backing_after']=snapshot('/e/profile-destination/'+c.label+'/destination/1/COMMITTED.json')
                        expected=r['aliases_before']['final'];old=expected['identity'].split(':')
                        assert r['final_backing_after']==dict(identity=':'.join(old[:2]+['1',old[3]]),sha256=expected['sha256'])
                        r['staging_absent_after']=execute('test ! -e '+c.destination+'/1/.staging/COMMITTED.part','1000:1000',False).returncode==0
                        r['payload_after']=snapshot('/e/profile-destination/'+c.label+'/destination/1/nested/data.bin')
                        assert r['staging_absent_after'] and r['payload_after']==r['payload_before']
                    if manifest_link:
                        r['manifest_final_after']=snapshot('/e/profile-destination/'+c.label+'/destination/1/COMMITTED.json')
                        before=r['manifest_staging_before']
                        assert r['manifest_final_after']==dict(identity=before['identity'],sha256=before['sha256'])
                        r['staging_absent_after']=execute('test ! -e '+c.destination+'/1/.staging/COMMITTED.part','1000:1000',False).returncode==0
                        r['payload_after']=snapshot('/e/profile-destination/'+c.label+'/destination/1/nested/data.bin')
                        assert r['staging_absent_after'] and r['payload_after']==r['payload_before']
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
    assert len(report['mover_cases'])==(8 if report.get('publication_sync_discovery') else 4) and all(c['passed'] for c in report['mover_cases'])
