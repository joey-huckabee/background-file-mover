"""Finite same-ID replay and queue refusal during multi-file partial source handoff."""
import json
import hashlib
import time


def qualify(Case,run,execute,client,server,output,relay,state,restore,snapshot,report):
    def clock():return int(run(['exec',relay.container,'python3','-c','import time; print(time.monotonic_ns())']).stdout)
    def custody(c):
        base='/e/profile-source/'+c.label+'/source'
        original=snapshot(base+'/current/nested/data.bin')
        present=run(['exec','--user','1000:1000',report['storage_reader'],'test','-e',base+'/.file-mover/1-1/data'],False).returncode==0
        private=snapshot(base+'/.file-mover/1-1/data') if present else None
        destination='/e/profile-destination/'+c.label+'/destination'
        run(['exec','--user','1000:1000',report['storage_reader'],'/bin/sh','-eu','-c','test -d '+destination+'; test ! -e '+destination+'/1'])
        if c.point=='claim_link_rpc':assert private is None and original['identity'].split(':')[2:]==['1','2097169']
        else:assert original==private and original['identity'].split(':')[2:]==['2','2097169']
        run(['exec','--user','1000:1000',report['storage_reader'],'/bin/sh','-eu','-c','test -d '+base+'/current/earlier; test ! -e '+base+'/current/earlier/first.bin'])
        first=snapshot(base+'/.file-mover/1-0/data')
        assert first==c.result['first_before']
        return dict(original=original,private=private,first=first,first_original_absent=True,delivery_absent=True)

    def verify(c):
        hashes=[]
        expected=[hashlib.sha256(b'first recording payload').hexdigest(),hashlib.sha256(bytes(2097152)+b'0123456789abcdefg').hexdigest()]
        names=['earlier/first.bin','nested/data.bin']
        for index,name in enumerate(names):
            lines=execute('sha256sum '+c.source+'/.file-mover/1-'+str(index)+'/data '+c.destination+'/1/'+name,'1000:1000').stdout.splitlines()
            assert [x.split()[0] for x in lines]==[expected[index]]*2
            hashes.append(lines)
        manifest=json.loads(execute('cat '+c.destination+'/1/COMMITTED.json','1000:1000').stdout)
        assert manifest['version']==1 and manifest['submission_id']==c.label and manifest['generator_id']=='fixture' and manifest['job_id']=='1'
        assert [(f['path'],f['size_bytes'],f['algorithm'],f['sha256']) for f in manifest['files']]==[(names[0],23,'sha256',expected[0]),(names[1],2097169,'sha256',expected[1])]
        assert execute(f"stat -c '%d:%i:%u:%a' {c.source} {c.source}/.file-mover {c.destination} {c.destination}/.file-mover",'1000:1000').stdout==c.identities
        assert snapshot('/e/profile-source/'+c.label+'/source/.file-mover/1-0/data')==c.result['first_before']
        c.result.update(hashes=hashes,manifest=manifest,root_identities_stable=True,source_retained=True,first_private_preserved=True)

    for profile in ('debug','release'):
        for phase in ('link','remove'):
            print('Partial handoff replay '+profile+' '+phase,flush=True)
            c=Case(profile,'claim_link_rpc' if phase=='link' else 'claim_unlink_rpc',suffix='-partial-handoff',both_nfs=True)
            r=c.result;report['mover_cases'].append(r);report['rust_executed']=True
            c.qualification_claim_index=1
            execute('mkdir -p '+c.source+"/current/earlier; printf 'first recording payload' >"+c.source+'/current/earlier/first.bin','1000:1000')
            c.body['files'].insert(0,dict(name='earlier/first.bin'))
            r['submission']=c.body
            r['first_before']=snapshot('/e/profile-source/'+c.label+'/source/current/earlier/first.bin')
            r['qualification_claim_index']=1
            c.config['max_retained_jobs']=1
            local=output/(c.label+'-replay-config.json');local.write_text(json.dumps(c.config),encoding='utf-8');run(['cp',str(local),client+':'+c.config_path])
            r.update(scenario_id='SC-137',phase=phase,config=c.config,burst_size=6)
            down=False
            try:
                original=c.source+'/current/nested/data.bin'
                stable="stat -c '%d:%i' "+c.base+'/state/jobs.sqlite; sha256sum '+c.config_path
                r['local_before']=execute(stable,'1000:1000').stdout
                relay.command('observe');c.start(True)
                posted=c.request('POST','/api/v2/jobs',c.body,asynchronous=True);c.await_pause()
                r['coordinator_pid']=c.service_pid();r['worker_pid']=c.worker
                r['status_before']=c.request('GET','/api/v2/jobs/1')[1];assert r['status_before']['state']=='Accepted' and not r['status_before']['source_paths_released']
                r['custody_before']=custody(c)
                r['before_server']=state();run(['exec',server,'rpc.nfsd','0']);down=True;r['stopped_server']=state();assert r['stopped_server']['threads']=='0'
                r['outage_started_ns']=clock();execute(': >'+c.rendezvous+'/go','1000:1000')
                for _ in range(40):
                    if c.state(c.worker)=='D':break
                    time.sleep(.1)
                raw=execute(f'cat /proc/{c.worker}/syscall').stdout.strip();fields=raw.split()
                assert c.state(c.worker)=='D' and len(fields)==9 and fields[0]==('265' if phase=='link' else '263')
                fd=int(fields[1],16);path=execute(f'readlink /proc/{c.worker}/fd/{fd}').stdout.strip();assert path==c.source+'/current/nested'
                r['blocked']=dict(state='D',syscall=raw,fd=fd,path=path,fdinfo=execute(f'cat /proc/{c.worker}/fdinfo/{fd}').stdout)
                if phase=='link':
                    newfd=int(fields[3],16);newpath=execute(f'readlink /proc/{c.worker}/fd/{newfd}').stdout.strip();assert newpath==c.source+'/.file-mover/1-1'
                    r['blocked'].update(newfd=newfd,newpath=newpath,newfdinfo=execute(f'cat /proc/{c.worker}/fdinfo/{newfd}').stdout)
                r['security']=execute(f'cat /proc/{c.worker}/status').stdout
                r['children_before']=c.children();assert r['children_before']==[c.worker]
                r['epoch_before']=json.loads(execute('cat '+c.base+'/state/workers.json','1000:1000').stdout)
                new=dict(c.body,submission_id=c.label+'-new',files=[dict(name='nested/missing.bin')]);r['new_body']=new
                pending=[(c.body,posted)]
                for i in range(6):
                    body=new if i%2==0 else c.body
                    pending.append((body,c.request('POST','/api/v2/jobs',body,asynchronous=True)))
                r['responses']=[]
                for body,(process,log) in pending:
                    process.wait(timeout=18);text=log.read_text(encoding='utf-8');code,response=c.parse(text)
                    r['responses'].append(dict(submission_id=body['submission_id'],raw=text,code=code,body=response,exit_code=process.returncode))
                    assert process.returncode==0 and code==503 and response['error'] in ('handoff_pending','service_busy') and response['retryable'] and not response['source_paths_released']
                assert any(x['body']['error']=='service_busy' for x in r['responses'])
                r['children_during']=c.children();assert r['children_during']==[c.worker] and c.state(c.worker)=='D'
                r['epoch_during']=json.loads(execute('cat '+c.base+'/state/workers.json','1000:1000').stdout);assert r['epoch_during']==r['epoch_before']
                began=time.monotonic();assert c.request('GET','/healthz')[0]==200;r['health_seconds']=time.monotonic()-began;assert r['health_seconds']<5
                r['status_during']=c.request('GET','/api/v2/jobs/1')[1];assert r['status_during']==r['status_before']
                r['retention_during']=c.request('GET','/api/v2/retention')[1];assert r['retention_during']['details']['retained_jobs']==1 and r['retention_during']['details']['confirmed_claims']==1 and all(v==0 for v in r['retention_during']['details']['destination_attempts_by_phase'].values())
                r['guard_exit']=execute('flock -n -E 73 '+c.base+'/state/instance.lock true','1000:1000',False).returncode;assert r['guard_exit']==73
                r['custody_during']=custody(c);assert r['custody_during']==r['custody_before']
                r['local_during']=execute(stable,'1000:1000').stdout;assert r['local_during']==r['local_before']
                r['still_stopped_server']=state();assert r['still_stopped_server']['threads']=='0'
                r['restore_started_ns']=clock();restore('nfsd');down=False;r['after_server']=state()
                r['retry_responses']=[]
                for _ in range(18):
                    code,response=c.request('POST','/api/v2/jobs',c.body);r['retry_responses'].append([code,response])
                    if code==202:break
                    assert code==503 and response['error'] in ('handoff_pending','service_busy') and response['retryable'] and not response['source_paths_released'];time.sleep(1)
                assert code==202 and response['job_id']=='1' and response['source_paths_released'];r['handoff']=response;r['handoff_ns']=clock()
                assert execute('test ! -e '+original,'1000:1000',False).returncode==0;r['original_absent_at_202']=True
                execute("printf 'next recording' >"+original+"; printf 'next first recording' >"+c.source+'/current/earlier/first.bin','1000:1000');r['source_reuse_ns']=clock()
                r['worker_exit']=c.await_exit(c.worker)
                r['committed']=c.recover(restart=False);assert len(r['committed']['details']['files'])==2 and all(f['attempt']==1 for f in r['committed']['details']['files']) and not r['committed']['details']['source_cleanup_enabled']
                assert c.service_pid()==r['coordinator_pid'];verify(c)
                r['producer_after']=execute('cat '+original,'1000:1000').stdout;assert r['producer_after']=='next recording';r['first_producer_after']=execute('cat '+c.source+'/current/earlier/first.bin','1000:1000').stdout;assert r['first_producer_after']=='next first recording'
                r['local_after']=execute(stable,'1000:1000').stdout;assert r['local_after']==r['local_before']
                r['private_after']=snapshot('/e/profile-source/'+c.label+'/source/.file-mover/1-1/data')
                old=r['custody_before']['original'];parts=old['identity'].split(':');assert r['private_after']==dict(identity=':'.join(parts[:2]+['1',parts[3]]),sha256=old['sha256'])
                code,response=c.request('POST','/api/v2/jobs',new);r['new_after']=[code,response];assert code==503 and response['error']=='retention_capacity' and not response['source_paths_released'] and response['retryable']
                assert c.request('GET','/api/v2/jobs/2')[0]==404
                r['wire']=relay.command('stop_observe')
                r['manifest_sha256']=execute('sha256sum '+c.destination+'/1/COMMITTED.json','1000:1000').stdout.split()[0]
                assert json.loads(execute(c.binary+' --stop '+c.config_path,'1000:1000').stdout)['phase']=='Stopped' and c.service.wait(timeout=30)==0
                c.worker=None;c.start(False);code,response=c.request('POST','/api/v2/jobs',c.body);r['replay']=response
                assert code==202 and response['job_id']=='1' and response['source_paths_released'] and c.request('GET','/api/v2/jobs/1')[1]['state']=='Committed'
                assert execute('cat '+original,'1000:1000').stdout=='next recording';assert execute('cat '+c.source+'/current/earlier/first.bin','1000:1000').stdout=='next first recording';verify(c)
                assert execute('sha256sum '+c.destination+'/1/COMMITTED.json','1000:1000').stdout.split()[0]==r['manifest_sha256']
                assert json.loads(execute(c.binary+' --stop '+c.config_path,'1000:1000').stdout)['phase']=='Stopped' and c.service.wait(timeout=30)==0
                r['original_state_preserved']=True;r['passed']=True;print('Partial handoff replay '+profile+' '+phase+': PASS',flush=True)
            finally:
                if down:restore('nfsd')
                c.cleanup()
                if 'wire' not in r:r['failed_wire']=relay.command('stop_observe')
