"""Finite source-claim REMOVE coordinator death before confirmed HTTP 202."""
import base64
import hashlib
import json
import sqlite3
import time
import zlib
from nfs_sync_support import start_trace,finish_trace


def qualify(Case,run,execute,spawn,client,server,output,containers,config,relay,state,restore,snapshot,report):
    stopped=None
    expected=hashlib.sha256(bytes(2097152)+b'0123456789abcdefg').hexdigest()
    reader=report['storage_reader']
    def resume():
        nonlocal stopped
        if stopped:restore(stopped);stopped=None
    def clock():return int(run(['exec',relay.container,'python3','-c','import time; print(time.monotonic_ns())']).stdout)
    def optional(path):
        lines=run(['exec','--user','1000:1000',reader,'/bin/sh','-eu','-c',
            'if test -e '+path+'; then stat -c %d:%i:%h:%s '+path+'; sha256sum '+path+'; fi']).stdout.splitlines()
        return dict(identity=lines[0],sha256=lines[1].split()[0]) if lines else None
    def source_names(c):
        base='/e/profile-source/'+c.label+'/source'
        return dict(original=optional(base+'/current/nested/data.bin'),private=optional(base+'/.file-mover/1-0/data'))
    def no_delivery(c):
        path='/e/profile-destination/'+c.label+'/destination/1'
        run(['exec','--user','1000:1000',reader,'test','!','-e',path])
        return dict(recording_directory_absent=True)
    def database(c,tag):
        folder=output/(c.label+'-'+tag);folder.mkdir();files={}
        for name in ('jobs.sqlite','jobs.sqlite-wal'):
            remote=c.base+'/state/'+name
            if execute('test -f '+remote,'1000:1000',False).returncode:
                assert name!='jobs.sqlite';continue
            before=execute('sha256sum '+remote,'1000:1000').stdout.split()[0]
            local=folder/name;run(['cp',client+':'+remote,str(local)]);data=local.read_bytes()
            assert hashlib.sha256(data).hexdigest()==before==execute('sha256sum '+remote,'1000:1000').stdout.split()[0]
            files[name]=dict(sha256=before,zlib_base64=base64.b64encode(zlib.compress(data,9)).decode())
        db=sqlite3.connect((folder/'jobs.sqlite').as_uri()+'?mode=ro',uri=True)
        try:
            db.execute('PRAGMA query_only=ON')
            claims=db.execute('SELECT job_id,file_index,source_name,private_name,source_identity,done FROM claims ORDER BY job_id,file_index').fetchall()
            jobs=db.execute('SELECT job_id,generator_id,submission_id FROM jobs ORDER BY job_id').fetchall()
            counts=[db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('transfers','manifests')]
        finally:db.close()
        assert len(claims)==1 and claims[0][:4]==(1,0,'current/nested/data.bin','1-0') and claims[0][5]==0
        assert jobs==[(1,'fixture',c.label)] and counts==[0,0]
        source=claims[0][4].split(':');identity=c.result['original_source'][0].split(':')
        assert source[:3]==['1',*identity[:2]] and source[3:5]==['1000','2097169'] and source[7]=='1'
        return dict(files=files,claims=[list(row) for row in claims],jobs=[list(row) for row in jobs],transfer_manifest_counts=counts,
                    observation='copied local database and existing WAL; no original SQLite opened')
    for profile in ('debug','release'):
        for kind in ('nfsd','container'):
            print('Claim REMOVE coordinator death '+profile+' '+kind,flush=True)
            c=Case(profile,'claim_unlink_rpc',suffix='-server-'+kind,both_nfs=True)
            r=c.result;report['mover_cases'].append(r);report['rust_executed']=True;observer=None
            r.update(kind=kind,scenario_id='SC-132',layout='two distinct retained tmpfs/client NFS filesystems, one server, local state',config=c.config)
            try:
                original=c.source+'/current/nested/data.bin'
                local_command="stat -c '%d:%i' "+c.base+'/state/jobs.sqlite; sha256sum '+c.config_path
                enrollment_command='sha256sum '+c.source+'/.file-mover/source-enrollment.json'
                r['original_source']=execute("stat -c '%d:%i:%s' "+original+'; sha256sum '+original,'1000:1000').stdout.splitlines()
                r['original_local_state']=execute(local_command,'1000:1000').stdout
                r['original_enrollment']=execute(enrollment_command,'1000:1000').stdout
                r['destination_device']=execute('stat -c %d '+c.destination,'1000:1000').stdout.strip()
                assert len({r['original_source'][0].split(':')[0],r['destination_device'],r['original_local_state'].splitlines()[0].split(':')[0]})==3
                relay.command('observe');c.start(True)
                posted=c.request('POST','/api/v2/jobs',c.body,asynchronous=True)
                c.await_pause();r['coordinator_pid']=c.service_pid();r['worker_pid']=c.worker
                r['status_before']=c.request('GET','/api/v2/jobs/1')[1];assert r['status_before']['state']=='Accepted'
                r['source_before']=source_names(c);r['delivery_before']=no_delivery(c)
                assert r['source_before']['original']['sha256']==expected and r['source_before']['original']['identity'].split(':')[2:]==['2','2097169']
                assert r['source_before']['private']==r['source_before']['original']
                r['initial_request_before_outage']=posted[1].read_text(encoding='utf-8')
                assert not r['initial_request_before_outage'].startswith('HTTP/1.1 202')
                if r['initial_request_before_outage'].startswith('HTTP/'):
                    code,body=c.parse(r['initial_request_before_outage']);assert code!=202 and not body['source_paths_released']
                r['epoch_before']=json.loads(execute('cat '+c.base+'/state/workers.json','1000:1000').stdout)
                assert r['epoch_before']['group']==int(r['coordinator_pid'])
                observer=start_trace(run,client,c.worker,containers,config,expected_exit='coordinator-death',io=True)
                r['clock_namespaces']={actor:run(['exec',actor,'readlink','/proc/self/ns/time']).stdout.strip() for actor in (client,observer,relay.container)}
                assert len(set(r['clock_namespaces'].values()))==1
                r['before_server']=state();r['before_wire']=relay.command('checkpoint');stopped=kind
                run(['exec',server,'rpc.nfsd','0'])
                if kind=='nfsd':r['stopped_server']=state();assert r['stopped_server']['threads']=='0'
                else:
                    r['quiesced_server']=state();assert r['quiesced_server']['threads']=='0'
                    run(['kill','--signal','KILL',server]);r['stop_exit_code']=int(run(['wait',server]).stdout.strip())
                    r['stopped_container']=json.loads(run(['inspect',server]).stdout)[0]['State']
                    assert r['stop_exit_code']==137 and r['stopped_container']['Status']=='exited' and r['stopped_container']['Pid']==0 and not r['stopped_container']['Running']
                r['source_stopped']=source_names(c);assert r['source_stopped']==r['source_before']
                execute(': >'+c.rendezvous+'/go','1000:1000')
                for _ in range(50):
                    if c.state(c.worker)=='D':break
                    assert c.service.poll() is None;time.sleep(.1)
                else:raise AssertionError('no actual pending claim REMOVE')
                raw=execute('cat /proc/'+c.worker+'/syscall').stdout.strip();fields=raw.split()
                assert len(fields)==9 and fields[0]=='263' and int(fields[3],16)==0
                fd=int(fields[1],16)
                path=execute(f'readlink /proc/{c.worker}/fd/{fd}').stdout.strip()
                assert path==c.source+'/current/nested' and c.children()==[c.worker]
                r['blocked_remove']=dict(state=c.state(c.worker),syscall=raw,fd=fd,path=path,
                    fdinfo=execute(f'cat /proc/{c.worker}/fdinfo/{fd}').stdout)
                assert r['blocked_remove']['state']=='D';r['worker_security']=execute('cat /proc/'+c.worker+'/status').stdout
                began=time.monotonic();assert c.request('GET','/healthz')[0]==200
                r['health_seconds']=time.monotonic()-began;assert r['health_seconds']<5
                r['status_during']=c.request('GET','/api/v2/jobs/1')[1];assert r['status_during']==r['status_before']
                r['local_state_during']=execute(local_command,'1000:1000').stdout;assert r['local_state_during']==r['original_local_state']
                r['guard_exit']=execute('flock -n -E 73 '+c.base+'/state/instance.lock true','1000:1000',False).returncode;assert r['guard_exit']==73
                contender_config=dict(c.config,bind='127.0.0.1:0');path=output/(c.label+'-contender.json');path.write_text(json.dumps(contender_config),encoding='utf-8')
                remote=c.base+'/contender.json';run(['cp',str(path),client+':'+remote])
                r['coordinator_kill_ns']=clock();c.signal(r['coordinator_pid'],'KILL')
                r['coordinator_exit_code']=c.service.wait(timeout=10);assert r['coordinator_exit_code']!=0 and c.state(r['coordinator_pid']) in ('','Z')
                posted[0].wait(timeout=15);response=posted[1].read_text(encoding='utf-8')
                r['interrupted_request']=dict(exit_code=posted[0].returncode,raw=response)
                if response.startswith('HTTP/'):
                    code,body=c.parse(response);assert code!=202 and not body['source_paths_released'];r['interrupted_request']['parsed']=[code,body]
                r['orphan_samples']=[]
                for _ in range(3):
                    sample=dict(worker_state=c.state(c.worker))
                    sample['guard_exit']=execute('flock -n -E 73 '+c.base+'/state/instance.lock true','1000:1000',False).returncode
                    status=execute(c.binary+' --status '+c.config_path,'1000:1000',False)
                    sample['status_exit']=status.returncode;sample['status']=json.loads(status.stdout);sample['worker_after']=c.state(c.worker)
                    assert sample['worker_state']==sample['worker_after']=='D' and sample['guard_exit'] in (0,73)
                    assert sample['status_exit']==2 and sample['status']['phase']=='OwnerUnavailable';r['orphan_samples'].append(sample)
                r['orphan_contenders']=[]
                for command,tail in (('', ''),('--initialize-source ',''),('--transfer-one ',' 1')):
                    began=time.monotonic();reply=execute(c.binary+' '+command+remote+tail,'1000:1000',False)
                    item=dict(command=command.strip() or 'service',exit_code=reply.returncode,stderr=reply.stderr,seconds=time.monotonic()-began,config=contender_config)
                    assert item['seconds']<6 and item['exit_code']!=0 and 'local instance or surviving worker already owns state' in item['stderr']
                    assert c.state(c.worker)=='D';r['orphan_contenders'].append(item)
                r['orphan_epoch']=json.loads(execute('cat '+c.base+'/state/workers.json','1000:1000').stdout);assert r['orphan_epoch']==r['epoch_before']
                r['source_orphan']=source_names(c);r['delivery_orphan']=no_delivery(c);assert r['source_orphan']==r['source_before']
                r['database_before_restore']=database(c,'before-restore')
                r['restore_started_ns']=clock();resume();r['after_server']=state()
                r['worker_exit']=c.await_exit(c.worker);r['worker_exit_observed_ns']=clock()
                r['trace']=finish_trace(run,observer);observer=None;c.worker=None
                r['source_settled']=source_names(c);r['delivery_settled']=no_delivery(c)
                old,new=r['source_settled']['original'],r['source_settled']['private'];assert old or new
                before=r['source_before']['original']
                for observed in (old,new):
                    if observed:
                        assert observed['sha256']==before['sha256'] and observed['identity'].split(':')[:2]==before['identity'].split(':')[:2]
                        assert observed['identity'].split(':')[2:]==(['2','2097169'] if old and new else ['1','2097169'])
                if old and new:assert old==new
                r['database_after_exit']=database(c,'after-exit');assert r['database_after_exit']==r['database_before_restore']
                status=execute(c.binary+' --status '+c.config_path,'1000:1000',False)
                r['status_after_exit']=json.loads(status.stdout);assert r['status_after_exit']['phase']=='NoActiveOwner'
                r['restart_started_ns']=clock();c.start(False)
                r['replacement_epoch']=json.loads(execute('cat '+c.base+'/state/workers.json','1000:1000').stdout)
                r['coordinator_after']=c.service_pid();assert r['replacement_epoch']['group']==int(r['coordinator_after'])!=r['epoch_before']['group']
                assert all(r['replacement_epoch'][k]==r['epoch_before'][k] for k in ('version','boot','namespace','guard'))
                r['retry_responses']=[]
                for _ in range(18):
                    code,body=c.request('POST','/api/v2/jobs',c.body);r['retry_responses'].append([code,body])
                    if code==202:break
                    assert code==503 and body['retryable'] and not body['source_paths_released'];time.sleep(1)
                assert code==202 and body['job_id']=='1' and body['source_paths_released']
                r['handoff']=body;r['retry_202_ns']=clock()
                assert execute('test ! -e '+original,'1000:1000',False).returncode==0;r['original_absent_at_202']=True
                execute("printf 'next recording' >"+original,'1000:1000');r['source_reuse_ns']=clock()
                committed=c.recover(False);r['committed']=committed
                assert committed['details']['files'][0]['attempt']==1 and not committed['details']['source_cleanup_enabled']
                c.verify();r['source_after']=source_names(c);r['final_payload']=snapshot('/e/profile-destination/'+c.label+'/destination/1/nested/data.bin')
                assert r['source_after']['private']['sha256']==expected and r['source_after']['private']['identity'].split(':')==before['identity'].split(':')[:2]+['1','2097169']
                assert r['source_after']['original']['sha256']==hashlib.sha256(b'next recording').hexdigest()
                r['local_state_after']=execute(local_command,'1000:1000').stdout;r['enrollment_after']=execute(enrollment_command,'1000:1000').stdout
                assert r['local_state_after']==r['original_local_state'] and r['enrollment_after']==r['original_enrollment']
                r['wire']=relay.command('stop_observe');manifest_hash=execute('sha256sum '+c.destination+'/1/COMMITTED.json','1000:1000').stdout.split()[0]
                assert json.loads(execute(c.binary+' --stop '+c.config_path,'1000:1000').stdout)['phase']=='Stopped' and c.service.wait(timeout=30)==0
                c.start(False);code,replay=c.request('POST','/api/v2/jobs',c.body)
                assert code==202 and replay['job_id']=='1' and replay['source_paths_released'] and c.request('GET','/api/v2/jobs/1')[1]['state']=='Committed'
                assert execute('cat '+original,'1000:1000').stdout=='next recording'
                assert execute('sha256sum '+c.destination+'/1/COMMITTED.json','1000:1000').stdout.split()[0]==manifest_hash
                assert execute(local_command,'1000:1000').stdout==r['original_local_state']
                c.verify();r['replay']=replay;r['original_state_preserved']=True
                assert json.loads(execute(c.binary+' --stop '+c.config_path,'1000:1000').stdout)['phase']=='Stopped' and c.service.wait(timeout=30)==0
                r['passed']=True;print('Claim REMOVE coordinator death '+profile+' '+kind+': PASS',flush=True)
            finally:
                resume();c.cleanup()
                if 'wire' not in r:r['failed_wire']=relay.command('stop_observe')
                if observer:r['incomplete_trace']=run(['logs',observer],False).stdout
