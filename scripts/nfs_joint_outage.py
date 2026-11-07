"""Finite claimed replay/revalidation/backpressure qualification during joint NFS outage."""
import json
import posixpath
import time


def qualify(Case,run,execute,spawn,client,server,output,config,relay,state,restore,snapshot,report):
    def clock():
        return int(run(['exec',relay.container,'python3','-c','import time; print(time.monotonic_ns())']).stdout)

    def children(c):
        rows=[]
        for pid in c.children():
            command=execute(f"tr '\\000' ' ' </proc/{pid}/cmdline",check=False).stdout
            rows.append(dict(pid=pid,command=command,state=c.state(pid)))
        return rows

    def blocked(c,pid):
        assert c.state(pid)=='D'
        raw=execute(f'cat /proc/{pid}/syscall').stdout.strip();fields=raw.split();assert len(fields)==9
        nr=int(fields[0]);args=[int(v,16) for v in fields[1:7]]
        row=dict(pid=pid,state='D',syscall=raw,number=nr)
        if nr in (257,262):
            # Read only this owned child's local proc memory, never an NFS pathname.
            memory=execute(f'dd if=/proc/{pid}/mem bs=1 skip={args[1]} count=512 2>/dev/null | od -An -v -tx1').stdout
            data=bytes.fromhex(memory);assert b'\0' in data
            pathname=data.split(b'\0',1)[0].decode('utf-8')
            directory=execute(f'readlink /proc/{pid}/'+('cwd' if args[0]&0xffffffff==0xffffff9c else 'fd/'+str(args[0]))).stdout.strip()
            path=pathname if pathname.startswith('/') else posixpath.normpath(posixpath.join(directory,pathname))
            row.update(path=path,pathname=pathname,pathname_hex=memory,directory=directory,directory_fd=args[0])
        else:
            assert nr in (0,5,138),raw
            row.update(fd=args[0],path=execute(f'readlink /proc/{pid}/fd/{args[0]}').stdout.strip(),fdinfo=execute(f'cat /proc/{pid}/fdinfo/{args[0]}').stdout)
        row['security']=execute(f'cat /proc/{pid}/status').stdout
        return row

    for profile in ('debug','release'):
        for enabled in (False,True):
            print('Joint outage '+profile+' admission '+str(enabled),flush=True)
            c=Case(profile,'verify_read',suffix='-joint-'+('on' if enabled else 'off'),both_nfs=True)
            r=c.result;report['mover_cases'].append(r);report['rust_executed']=True
            c.config['max_retained_jobs']=1
            if enabled:c.config['source_space_admission']=dict(enabled=True,min_available_bytes=1,max_sample_age_seconds=1,probe_timeout_seconds=1)
            local=output/(c.label+'-joint-config.json');local.write_text(json.dumps(c.config),encoding='utf-8')
            run(['cp',str(local),client+':'+c.config_path])
            r.update(scenario_id='SC-135',config=c.config,admission_enabled=enabled,layout='two distinct retained NFS filesystems, shared NFSD, local state',burst_size=6)
            down=False
            try:
                original=c.source+'/current/nested/data.bin'
                stable="stat -c '%d:%i' "+c.base+'/state/jobs.sqlite; sha256sum '+c.config_path
                r['local_before']=execute(stable,'1000:1000').stdout
                relay.command('observe');c.start(True)
                code,handoff=c.request('POST','/api/v2/jobs',c.body);assert code==202 and handoff['source_paths_released'];r['handoff']=handoff
                c.await_pause();r['coordinator_pid']=c.service_pid();r['delivery_pid']=c.worker
                execute("printf 'next recording' >"+original,'1000:1000')
                r['status_before']=c.request('GET','/api/v2/jobs/1')[1]
                assert r['status_before']['state']=='Claimed' and r['status_before']['details']['files'][0]['transfer_phase']=='Copied'
                r['source_before']=snapshot('/e/profile-source/'+c.label+'/source/.file-mover/1-0/data')
                r['destination_before']=snapshot('/e/profile-destination/'+c.label+'/destination/1/.staging/1.part')
                assert r['source_before']['sha256']==r['destination_before']['sha256']
                r['before_server']=state();run(['exec',server,'rpc.nfsd','0']);down=True;r['stopped_server']=state();assert r['stopped_server']['threads']=='0'
                r['outage_started_ns']=clock();execute(': >'+c.rendezvous+'/go','1000:1000')
                for _ in range(30):
                    if c.state(c.worker)=='D':break
                    time.sleep(.1)
                r['delivery_blocked']=blocked(c,c.worker)
                assert r['delivery_blocked']['number']==0 and r['delivery_blocked']['path']==c.destination+'/1/.staging/1.part'
                # Age this fixture's cached source metadata; actual blocked validation
                # below, not the delay itself, is the required evidence.
                began=time.monotonic()
                while time.monotonic()-began<65:time.sleep(1)
                r['aged_seconds']=time.monotonic()-began;r['after_age_ns']=clock()
                new=dict(c.body,submission_id=c.label+'-new',files=[dict(name='nested/missing.bin')]);r['new_body']=new
                if enabled:
                    began=time.monotonic();code,body=c.request('POST','/api/v2/jobs',new)
                    r['new_probe_reply']=dict(code=code,body=body,seconds=time.monotonic()-began)
                    assert code==503 and body['error']=='source_space_unavailable' and body['retryable'] and not body['source_paths_released']
                replay=c.request('POST','/api/v2/jobs',c.body,asynchronous=True)
                for _ in range(35):
                    cs=children(c);claims=[x for x in cs if '--internal-claim-worker' in x['command'] and x['state']=='D']
                    if claims:break
                    time.sleep(.1)
                else:raise AssertionError('same-ID replay did not prove blocked source revalidation')
                assert len(claims)==1;r['validation_blocked']=blocked(c,claims[0]['pid'])
                assert r['validation_blocked']['path']=='/tmp/recovery-source' or r['validation_blocked']['path'].startswith('/tmp/recovery-source/')
                r['children_before_burst']=cs
                pending=[(c.body,replay)]
                for i in range(6):
                    body=new if i%2==0 else c.body
                    pending.append((body,c.request('POST','/api/v2/jobs',body,asynchronous=True)))
                r['responses']=[]
                for body,(process,log) in pending:
                    process.wait(timeout=18);raw=log.read_text(encoding='utf-8');code,response=c.parse(raw)
                    r['responses'].append(dict(submission_id=body['submission_id'],raw=raw,code=code,body=response,exit_code=process.returncode))
                    assert process.returncode==0 and code==503 and response['error'] in ('handoff_pending','service_busy') and response['retryable'] and not response['source_paths_released']
                assert any(x['body']['error']=='service_busy' for x in r['responses'])
                r['children_after_burst']=children(c)
                essential=lambda rows:[x for x in rows if '--internal-source-space-worker' not in x['command']]
                assert essential(cs)==essential(r['children_after_burst']) and len(essential(cs))==2
                for rows in (cs,r['children_after_burst']):
                    probes=[x for x in rows if '--internal-source-space-worker' in x['command']]
                    assert len(rows)==2+len(probes) and len(probes)<=(1 if enabled else 0)
                after_pids={x['pid'] for x in r['children_after_burst']}
                r['exited_probes']={x['pid']:c.state(x['pid']) or 'gone' for x in cs if '--internal-source-space-worker' in x['command'] and x['pid'] not in after_pids}
                assert all(v in ('gone','Z') for v in r['exited_probes'].values())
                began=time.monotonic();assert c.request('GET','/healthz')[0]==200;r['health_seconds']=time.monotonic()-began;assert r['health_seconds']<5
                r['status_during']=c.request('GET','/api/v2/jobs/1')[1];assert r['status_during']==r['status_before']
                r['retention_during']=c.request('GET','/api/v2/retention')[1]
                assert r['retention_during']['details']['retained_jobs']==1
                r['guard_exit']=execute('flock -n -E 73 '+c.base+'/state/instance.lock true','1000:1000',False).returncode;assert r['guard_exit']==73
                r['source_during']=snapshot('/e/profile-source/'+c.label+'/source/.file-mover/1-0/data');assert r['source_during']==r['source_before']
                r['destination_during']=snapshot('/e/profile-destination/'+c.label+'/destination/1/.staging/1.part');assert r['destination_during']==r['destination_before']
                assert run(['exec',report['storage_reader'],'test','!','-e','/e/profile-destination/'+c.label+'/destination/1/COMMITTED.json'],False).returncode==0
                r['manifest_absent_during']=True;r['still_stopped_server']=state();assert r['still_stopped_server']['threads']=='0'
                r['restore_started_ns']=clock();restore('nfsd');down=False;r['after_server']=state()
                r['committed']=c.recover(restart=False);assert r['committed']['details']['files'][0]['attempt']==1 and not r['committed']['details']['source_cleanup_enabled']
                assert c.service_pid()==r['coordinator_pid'];r['delivery_exit']=c.await_exit(c.worker)
                r['validation_exit']=c.await_exit(claims[0]['pid']);c.verify()
                assert execute('cat '+original,'1000:1000').stdout=='next recording'
                r['retention_after']=c.request('GET','/api/v2/retention')[1];assert r['retention_after']['details']['retained_jobs']==1
                code,response=c.request('POST','/api/v2/jobs',new);r['new_after']=[code,response]
                assert code==503 and response['error']=='retention_capacity' and response['retryable'] and not response['source_paths_released']
                assert c.request('GET','/api/v2/jobs/2')[0]==404
                assert execute(stable,'1000:1000').stdout==r['local_before']
                r['wire']=relay.command('stop_observe')
                assert json.loads(execute(c.binary+' --stop '+c.config_path,'1000:1000').stdout)['phase']=='Stopped' and c.service.wait(timeout=30)==0
                c.worker=None;c.start(False);code,response=c.request('POST','/api/v2/jobs',c.body);r['replay']=response
                assert code==202 and response['job_id']=='1' and response['source_paths_released']
                assert execute('cat '+original,'1000:1000').stdout=='next recording';c.verify()
                assert json.loads(execute(c.binary+' --stop '+c.config_path,'1000:1000').stdout)['phase']=='Stopped' and c.service.wait(timeout=30)==0
                r['original_state_preserved']=True;r['passed']=True;print('Joint outage '+profile+' admission '+str(enabled)+': PASS',flush=True)
            finally:
                if down:restore('nfsd')
                c.cleanup()
                if 'wire' not in r:r['failed_wire']=relay.command('stop_observe')
