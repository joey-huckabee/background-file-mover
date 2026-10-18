"""Selected source-claim reply loss; preserve the producer's unconfirmed handoff."""
import json
import time
import traceback
from nfs_bootstrap_state import receipt_evidence
from nfs_reply_relay import server_objects


def qualify(Case, run, execute, spawn, restore, output, client, results, endpoints, relay):
    def status(c, phase):
        began = time.monotonic()
        reply = execute(f'{c.binary} --status {c.config_path}', '1000:1000', check=False)
        value = json.loads(reply.stdout)
        row = dict(exit_code=reply.returncode, seconds=round(time.monotonic() - began, 3), snapshot=value)
        assert row['seconds'] < 5 and value['phase'] == phase, row
        assert reply.returncode == (2 if phase == 'OwnerUnavailable' else 0), row
        return row

    def tasks(main, worker):
        lines = execute(f'for f in /proc/{main}/task/*/stat /proc/{worker}/task/*/stat; do '
                        'test ! -r "$f" || cat "$f" 2>/dev/null || true; done', '1000:1000').stdout.splitlines()
        return [dict(tid=int(v.split()[0]), state=v.rsplit(') ', 1)[1].split()[0]) for v in lines]

    def exited(rows):
        return all(t['state'] in {'Z', 'X', 'x'} for t in rows)


    def pending_submission(c, posted):
        process, path = posted
        process.wait(timeout=15)
        text = path.read_text(encoding='utf-8')
        response = c.parse(text)
        assert response[0] == 503 and response[1]['retryable']
        assert not response[1]['source_paths_released']
        assert response[1]['error'] in {'handoff_pending', 'service_busy'}
        return dict(exit_code=process.returncode, response=response)

    server = endpoints.servers['source']
    for profile in ('debug', 'release'):
        for point, operation in (('claim_link_rpc', 11), ('claim_unlink_rpc', 28)):
            c = None
            result = dict(profile=profile, point=point, operation=operation, passed=False, scenario_id='SC-100')
            try:
                c = Case(profile, point, suffix='-sr', both_nfs=True,
                         separate_exports=True, independent_endpoints=True)
                c.result.update(result)
                result = c.result
                remote = c.source.replace('/tmp/nfs-source/', '/exports/death-source/', 1)
                original_path = remote + '/current/nested/data.bin'
                private_path = remote + '/.file-mover/1-0/data'
                initial = server_objects(run, server, original_path, private_path)
                assert initial['old']['links'] == 1 and initial['final'] is None
                result['server_before_submission'] = initial
                c.start(True)
                posted = c.request('POST', '/api/v2/jobs', c.body, asynchronous=True)
                c.await_pause()
                main, worker = c.service_pid(), c.worker
                result['database_identity_before'] = execute(f"stat -c '%d:%i' {c.base}/state/jobs.sqlite", '1000:1000').stdout
                result['enrollment_receipt_before'] = receipt_evidence(c, execute)
                security = execute(f'cat /proc/{worker}/status', '1000:1000').stdout
                fields = {k:v.strip() for line in security.splitlines() if ':' in line
                          for k,v in [line.split(':',1)] if k in {'Uid','Gid','CapInh','CapPrm','CapEff','NoNewPrivs'}}
                assert fields['Uid'].split() == fields['Gid'].split() == ['1000']*4
                assert fields['NoNewPrivs']=='1' and all(int(fields[k],16)==0 for k in ('CapInh','CapPrm','CapEff'))
                result['worker_security'] = fields
                epoch = json.loads(execute(f'cat {c.base}/state/workers.json','1000:1000').stdout)
                assert epoch['group'] == int(main)
                result['worker_epoch_before_death'] = epoch
                result['relay_armed'] = relay.command('arm', 'data' if operation==11 else 'data.bin', operation)
                execute(f'umask 077; : >{c.rendezvous}/go','1000:1000')
                result['reply_withheld'] = relay.await_held()
                assert c.state(worker)=='D'
                raw = execute(f'cat /proc/{worker}/syscall').stdout.strip()
                words = raw.split()
                assert len(words)==9 and words[0]==('265' if operation==11 else '263'),raw
                fd = int(words[1],16)
                parent = execute(f'readlink /proc/{worker}/fd/{fd}','1000:1000').stdout.strip()
                assert parent==c.source+'/current/nested'
                syscall = dict(raw=raw, old_parent=parent)
                if operation==11:
                    new_fd = int(words[3],16)
                    syscall['new_parent'] = execute(f'readlink /proc/{worker}/fd/{new_fd}','1000:1000').stdout.strip()
                    assert syscall['new_parent']==c.source+'/.file-mover/1-0' and int(words[5],16)==0
                else:
                    assert int(words[3],16)==0
                result['blocked_claim_syscall'] = syscall
                completed = server_objects(run,server,original_path,private_path)
                result['server_completed_with_reply_withheld'] = completed
                assert completed['final']['links']==(2 if operation==11 else 1)
                assert completed['old']==(completed['final'] if operation==11 else None)
                assert all(completed['final'][k]==initial['old'][k] for k in ('device','inode','size','sha256'))
                result['server_threads_while_withheld'] = {role:run(['exec',target,'cat','/proc/fs/nfsd/threads']).stdout.strip() for role,target in endpoints.servers.items()}
                assert set(result['server_threads_while_withheld'].values())=={'2'}
                result['healthy_source'] = endpoints.healthy('source')
                result['healthy_destination'] = endpoints.healthy('destination')
                for key,method,path,body in (('health','GET','/healthz',None),('job','GET','/api/v2/jobs/1',None),('replay','POST','/api/v2/jobs',c.body)):
                    began=time.monotonic(); response=c.request(method,path,body)
                    result[key]=dict(seconds=round(time.monotonic()-began,3),response=response)
                    assert result[key]['seconds'] < (15 if key=='replay' else 5)
                assert result['health']['response'][0]==200
                job=result['job']['response'][1]
                assert result['job']['response'][0]==200 and job['state']=='Accepted'
                assert job['source_paths_released'] is False and job['details']['source_cleanup_enabled'] is False
                replay=result['replay']['response']
                assert replay[0]==503 and replay[1]['retryable'] and not replay[1]['source_paths_released']
                assert replay[1]['error'] in {'handoff_pending','service_busy'}
                result['initial_submission']=pending_submission(c,posted)
                began=time.monotonic(); after_retry=c.request('GET','/api/v2/jobs/1')
                result['job_after_retry']=dict(seconds=round(time.monotonic()-began,3),response=after_retry)
                assert result['job_after_retry']['seconds']<5 and after_retry[0]==200
                assert after_retry[1]['state']=='Accepted' and after_retry[1]['source_paths_released'] is False
                assert execute(f'test ! -e {c.destination}/1','1000:1000',check=False).returncode==0
                assert c.children()==[worker] and c.state(worker)=='D'
                result['relay_before_coordinator_death']=relay.await_held()
                c.signal(main,'KILL'); assert c.service.wait(timeout=10)!=0
                old_tasks=tasks(main,worker);result['old_tasks_after_coordinator_death']=old_tasks
                if not exited(old_tasks):
                    result['orphan_status']=status(c,'OwnerUnavailable')
                    assert json.loads(execute(f'cat {c.base}/state/workers.json','1000:1000').stdout)==epoch
                    path=output/(c.label+'-competitor.json')
                    path.write_text(json.dumps(dict(c.config,bind='127.0.0.1:0')),encoding='utf-8')
                    remote_config=c.base+'/competitor.json'
                    run(['cp',str(path),client+':'+remote_config])
                    process=spawn(f'exec {c.binary} {remote_config}',c.label+'-competitor');c.processes.append(process)
                    assert process.wait(timeout=6)!=0
                    diagnostic=(output/(c.label+'-competitor.log')).read_text(encoding='utf-8')
                    assert 'local instance or surviving worker already owns state' in diagnostic
                    result['contender_refused']=diagnostic.strip()
                    result['outcome']='surviving_worker_excludes_replacement'
                    c.signal(worker,'KILL')
                else:
                    result['outcome']='worker_exited_after_coordinator_death'
                discarded=relay.command('drop');result['reply_discarded']=discarded
                assert discarded['dropped'] and not discarded['released'] and discarded['connection_resets']
                assert not {r['receive_id'] for r in discarded['dropped']} & {r['receive_id'] for r in discarded['forwarded']}
                c.await_exit(main);result['worker_exit']=c.await_exit(worker)
                for _ in range(30):
                    old_tasks=tasks(main,worker)
                    if exited(old_tasks):break
                    time.sleep(.2)
                else:raise AssertionError('old claim threads still live')
                result['old_threads_before_recovery']=old_tasks;c.worker=None
                result['status_after_old_exit']=status(c,'NoActiveOwner')
                observed=server_objects(run,server,original_path,private_path)
                assert observed==completed
                result['source_after_old_exit']=observed
                c.start(False)
                code,accepted=c.request('POST','/api/v2/jobs',c.body)
                assert code==202 and accepted['job_id']=='1' and accepted['source_paths_released']
                result['confirmed_custody_replay']=[code,accepted]
                # The producer reuses its path only after confirmed 202.
                execute(f"printf 'next recording' >{c.source}/current/nested/data.bin",'1000:1000')
                result['producer_reuse_after_202']=True
                final=c.recover(restart=False)
                assert final['details']['files'][0]['attempt']==1 and final['details']['source_cleanup_enabled'] is False
                c.verify()
                after=server_objects(run,server,original_path,private_path)
                assert after['final']['links']==1
                assert all(after['final'][k]==initial['old'][k] for k in ('device','inode','size','sha256'))
                assert execute(f'cat {c.source}/current/nested/data.bin','1000:1000').stdout=='next recording'
                result['source_after_recovery']=after
                second=c.request('GET','/api/v2/jobs/2')
                assert second[0]==404 and second[1]['error']=='not_found'
                result['second_job_absent']=second
                result['database_identity_after']=execute(f"stat -c '%d:%i' {c.base}/state/jobs.sqlite",'1000:1000').stdout
                result['enrollment_receipt_after']=receipt_evidence(c,execute)
                assert result['database_identity_after']==result['database_identity_before']
                assert result['enrollment_receipt_after']==result['enrollment_receipt_before']
                assert execute(f'test ! -e {c.source}/.file-mover/2-0 && test ! -e {c.destination}/1/.staging/2.part','1000:1000',check=False).returncode==0
                result.update(original_claim_inode_preserved=True,original_state_recovery=True,passed=True,relay_after_recovery=relay.state())
            except Exception as error:
                result.update(error=f'{type(error).__name__}: {error}',traceback=traceback.format_exc())
            finally:
                if c:
                    try:
                        c.cleanup();result['final_status']=status(c,'NoActiveOwner')
                    except Exception as error:result.update(cleanup_error=str(error),passed=False)
                results.append(result)
                print(f"NFS source claim reply {profile}/{point}: {'PASS' if result['passed'] else 'FAILED'}",flush=True)
            if not result['passed']:return dict(passed=False)
    return dict(passed=len(results)==4 and all(r['passed'] for r in results),scope='claim-lost-reply',core_cases=len(results))
