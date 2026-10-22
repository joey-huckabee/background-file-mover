"""Finite healthy-NFS source identity/size refusal after a partial handoff."""
import base64
import hashlib
import json
import sqlite3
import time
import zlib


def qualify(Case,run,execute,client,server,output,relay,state,restore,snapshot,report):
    def clock():return int(run(['exec',relay.container,'python3','-c','import time; print(time.monotonic_ns())']).stdout)
    def metadata(path):
        rows=execute("stat --printf '%d\\n%i\\n%u\\n%s\\n%Y\\n%y\\n%h' "+path,'1000:1000').stdout.splitlines()
        assert len(rows)==7
        nanos=rows[5].split('.')[1].split()[0];assert len(nanos)==9
        return '1:'+':'.join(rows[:5]+[str(int(nanos)),rows[6]])
    def custody(c):
        base='/e/profile-source/'+c.label+'/source';reader=report['storage_reader']
        run(['exec','--user','1000:1000',reader,'/bin/sh','-eu','-c','test -d '+base+'/current/earlier; test ! -e '+base+'/current/earlier/first.bin; test -d '+base+'/.file-mover/1-1; test ! -e '+base+'/.file-mover/1-1/data'])
        dest='/e/profile-destination/'+c.label+'/destination'
        run(['exec','--user','1000:1000',reader,'/bin/sh','-eu','-c','test -d '+dest+'; test ! -e '+dest+'/1'])
        first=snapshot(base+'/.file-mover/1-0/data');assert first==c.result['first_before']
        return dict(first=first,original=snapshot(base+'/current/nested/data.bin'),saved=snapshot(base+'/fixture-original'),first_original_absent=True,second_private_absent=True,delivery_absent=True)
    def database(c,tag):
        # Copy only a quiescent paused assignment or normally stopped service.
        # Read the copies, never open the original SQLite through Python.
        folder=output/(c.label+'-'+tag);folder.mkdir();files={};hashes={}
        for name in ('jobs.sqlite','jobs.sqlite-wal'):
            path=c.base+'/state/'+name
            if execute('test -f '+path,'1000:1000',False).returncode:
                assert name!='jobs.sqlite';continue
            before=execute('sha256sum '+path,'1000:1000').stdout.split()[0]
            local=folder/name;run(['cp',client+':'+path,str(local)]);data=local.read_bytes()
            assert hashlib.sha256(data).hexdigest()==before
            hashes[name]=before;files[name]=dict(sha256=before,zlib_base64=base64.b64encode(zlib.compress(data,9)).decode())
        for name,before in hashes.items():assert execute('sha256sum '+c.base+'/state/'+name,'1000:1000').stdout.split()[0]==before
        with sqlite3.connect((folder/'jobs.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as db:
            db.execute('PRAGMA query_only=ON')
            claims=[list(row) for row in db.execute('SELECT * FROM claims ORDER BY job_id,file_index')]
            counts={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('jobs','files','claims','transfers','manifests')}
        assert counts==dict(jobs=1,files=2,claims=2,transfers=0,manifests=0) and [row[-1] for row in claims]==[1,0]
        return dict(files=files,claims=claims,counts=counts)
    def check_status(c):
        code,status=c.request('GET','/api/v2/jobs/1');assert code==200 and status['state']=='Accepted' and not status['source_paths_released']
        retention=c.request('GET','/api/v2/retention')[1]
        assert retention['details']['retained_jobs']==1 and retention['details']['confirmed_claims']==1 and all(v==0 for v in retention['details']['destination_attempts_by_phase'].values())
        assert not status['details']['source_cleanup_enabled']
        return dict(status=status,retention=retention)
    def stop(c):
        response=json.loads(execute(c.binary+' --stop '+c.config_path,'1000:1000').stdout)
        assert response['phase']=='Stopped' and c.service.wait(timeout=30)==0
        c.worker=None
        return response

    for profile in ('debug','release'):
        for phase in ('inode','size'):
            print('Source-change refusal '+profile+' '+phase,flush=True)
            c=Case(profile,'claim_apply',suffix='-source-change-'+phase,both_nfs=True)
            r=c.result;report['mover_cases'].append(r);report['rust_executed']=True
            r.update(scenario_id='SC-138',phase=phase,config=c.config,qualification_claim_index=1)
            c.qualification_claim_index=1
            execute('mkdir -p '+c.source+"/current/earlier; printf 'first recording payload' >"+c.source+'/current/earlier/first.bin','1000:1000')
            c.body['files'].insert(0,dict(name='earlier/first.bin'));r['submission']=c.body
            base='/e/profile-source/'+c.label+'/source';original=c.source+'/current/nested/data.bin';saved=c.source+'/fixture-original'
            r['first_before']=snapshot(base+'/current/earlier/first.bin')
            try:
                stable="stat -c '%d:%i' "+c.base+'/state/jobs.sqlite; sha256sum '+c.config_path
                r['local_before']=execute(stable,'1000:1000').stdout
                r['before_server']=state();assert r['before_server']['threads']=='2'
                relay.command('observe');c.start(True)
                posted=c.request('POST','/api/v2/jobs',c.body,asynchronous=True);c.await_pause()
                r['coordinator_pid']=c.service_pid();r['worker_pid']=c.worker
                r['pending_database']=database(c,'pending')
                r['original_before']=snapshot(base+'/current/nested/data.bin');r['identity_before']=metadata(original)
                assert r['pending_database']['claims'][1][-2]==r['identity_before']
                r['mutation_started_ns']=clock()
                if phase=='inode':execute('cp -p '+original+' '+original+'.replacement; mv '+original+' '+saved+'; mv '+original+'.replacement '+original,'1000:1000')
                else:execute('cp -p '+original+' '+saved+"; printf X >>"+original+'; touch -r '+saved+' '+original,'1000:1000')
                r['identity_changed']=metadata(original);r['changed_custody']=custody(c);r['mutation_completed_ns']=clock()
                old=r['identity_before'].split(':');changed=r['identity_changed'].split(':')
                if phase=='inode':assert old[2]!=changed[2] and old[:2]+old[3:]==changed[:2]+changed[3:] and r['original_before']['sha256']==r['changed_custody']['original']['sha256']
                else:assert old[:4]+old[5:]==changed[:4]+changed[5:] and int(changed[4])==int(old[4])+1 and r['original_before']['sha256']!=r['changed_custody']['original']['sha256']
                execute(': >'+c.rendezvous+'/go','1000:1000')
                r['worker_exit']=c.await_exit(c.worker)
                process,log=posted;process.wait(timeout=18);text=log.read_text(encoding='utf-8');code,body=c.parse(text)
                r['initial_response']=dict(raw=text,code=code,body=body,exit_code=process.returncode)
                assert process.returncode==0 and not body['source_paths_released'] and (code==409 and body['error']=='recording_blocked' and not body['retryable'] or code==503 and body['error']=='handoff_pending' and body['retryable'])
                r['after_refusal']=check_status(c);r['after_refusal_custody']=custody(c);assert r['after_refusal_custody']==r['changed_custody'];r['guard_exit']=execute('flock -n -E 73 '+c.base+'/state/instance.lock true','1000:1000',False).returncode;assert r['guard_exit']==73
                r['stop_initial']=stop(c);r['initial_diagnostic']=(output/c.service_logs[-1]).read_text(encoding='utf-8');assert 'apply: blocked: relocation object changed' in r['initial_diagnostic'];r['stopped_database']=database(c,'stopped')
                assert r['stopped_database']['claims']==r['pending_database']['claims']
                r['restarts']=[]
                for index in range(2):
                    c.start(False);row=dict(coordinator_pid=c.service_pid(),responses=[]);r['restarts'].append(row)
                    for _ in range(3):
                        code,body=c.request('POST','/api/v2/jobs',c.body);row['responses'].append([code,body])
                        assert code==409 and body['error']=='recording_blocked' and not body['retryable'] and not body['source_paths_released'] and body['job_id']=='1'
                    row.update(check_status(c));row['custody']=custody(c);assert row['custody']==r['changed_custody']
                    row['identity']=metadata(original);assert row['identity']==r['identity_changed']
                    row['stop']=stop(c);row['database']=database(c,'restart-'+str(index));assert row['database']['claims']==r['pending_database']['claims']
                r['wire']=relay.command('stop_observe');r['after_server']=state()
                r['local_after']=execute(stable,'1000:1000').stdout;assert r['local_after']==r['local_before']
                r['root_identities_stable']=execute(f"stat -c '%d:%i:%u:%a' {c.source} {c.source}/.file-mover {c.destination} {c.destination}/.file-mover",'1000:1000').stdout==c.identities
                assert r['root_identities_stable']
                r['passed']=True;print('Source-change refusal '+profile+' '+phase+': PASS',flush=True)
            finally:
                c.cleanup()
                if 'wire' not in r:r['failed_wire']=relay.command('stop_observe')
