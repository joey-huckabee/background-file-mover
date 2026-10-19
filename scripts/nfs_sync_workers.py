"""Finite healthy-service syscall/RPC correlation; no invented sync-loss cases."""
import json,time,traceback
from nfs_bootstrap_state import receipt_evidence
from nfs_sync_support import start_trace,finish_trace,correlate


def qualify(Case,run,execute,spawn,restore,output,client,results,endpoints,relays,containers,config):
 for profile in ('debug','release'):
  for point,role in (('claim_apply','source'),('copy_chunk','destination')):
   c=None;result=dict(profile=profile,point=point,role=role,passed=False,scenario_id='SC-101')
   try:
    c=Case(profile,point,suffix='-so',both_nfs=True,separate_exports=True,independent_endpoints=True);c.result.update(result);result=c.result
    c.start(True);posted=c.request('POST','/api/v2/jobs',c.body,asynchronous=True);c.await_pause();pid=c.worker
    assert execute(f'ls /proc/{pid}/task','1000:1000').stdout.split()==[pid]
    sec=execute(f'cat /proc/{pid}/status','1000:1000').stdout
    fields={k:v.strip() for line in sec.splitlines() if ':' in line for k,v in [line.split(':',1)] if k in {'Uid','Gid','CapInh','CapPrm','CapEff','NoNewPrivs'}}
    assert fields['Uid'].split()==fields['Gid'].split()==['1000']*4 and fields['NoNewPrivs']=='1'
    assert all(int(fields[k],16)==0 for k in ('CapInh','CapPrm','CapEff'));result['worker_security']=fields
    result['database_identity_before']=execute(f"stat -c '%d:%i' {c.base}/state/jobs.sqlite",'1000:1000').stdout
    result['enrollment_before']=receipt_evidence(c,execute)
    observer=start_trace(run,client,int(pid),containers,config,expected_exit='supervised-delivery' if point=='copy_chunk' else 'zero');relay=relays[role];relay.command('observe')
    execute(f'touch {c.rendezvous}/go','1000:1000')
    # Finish the actual worker before stopping observation. Single-file delivery
    # includes payload sync, publication and manifest sync in this worker.
    c.await_exit(pid);c.worker=None;trace=finish_trace(run,observer);wire=relay.command('stop_observe');result['trace']=correlate(trace,wire);result['wire']=wire
    if point=='copy_chunk':
     code,receipt=c.request('GET','/api/v2/jobs/1');assert code==200 and receipt['state']=='Committed' and receipt['details']['files'][0]['attempt']==1
     result['retirement_committed_receipt']=receipt
    target=endpoints.mounts[role]+'/'
    syncs=[s for s in trace['syncs'] if s['path'].startswith(target)]
    assert syncs and all(s['result']==0 for s in syncs)
    result['nfs_syncs']=syncs
    posted[0].wait(timeout=15);result['initial_response']=c.parse(posted[1].read_text(encoding='utf-8'))
    initial=result['initial_response'];assert (initial[0]==202 and initial[1]['source_paths_released']) or (initial[0]==503 and initial[1]['retryable'] and not initial[1]['source_paths_released'])
    code,accepted=c.request('POST','/api/v2/jobs',c.body);assert code==202 and accepted['job_id']=='1' and accepted['source_paths_released'];result['confirmed_response']=[code,accepted]
    execute(f"printf 'next recording' >{c.source}/current/nested/data.bin",'1000:1000')
    final=c.recover(restart=False);c.verify()
    result['source_private_identity_after']=execute(f"stat -c '%d:%i:%s' {c.source}/.file-mover/1-0/data",'1000:1000').stdout.strip()
    assert result['source_private_identity_after']==result['source_payload_at_setup'][0]
    result['enrollment_after']=receipt_evidence(c,execute);assert result['enrollment_before']==result['enrollment_after']
    assert final['details']['files'][0]['attempt']==1 and final['details']['source_cleanup_enabled'] is False
    assert execute(f'cat {c.source}/current/nested/data.bin','1000:1000').stdout=='next recording'
    result['database_identity_after']=execute(f"stat -c '%d:%i' {c.base}/state/jobs.sqlite",'1000:1000').stdout;assert result['database_identity_before']==result['database_identity_after']
    result['interceptable_sync_operations']=sorted({op['op'] for s in syncs for call in s['rpc_calls'] if call['decoded'] for op in call['decoded']['operations'] if op['op'] in (5,38)})
    result['sync_loss_tested']=False;result['producer_reuse_after_202']=True;result['passed']=True
   except Exception as error:result.update(error=str(error),traceback=traceback.format_exc())
   finally:
    if c:
     try:c.cleanup()
     except Exception as error:result.update(cleanup_error=str(error),passed=False)
    results.append(result);print(f"NFS sync observation {profile}/{point}: {'PASS' if result['passed'] else 'FAILED'}",flush=True)
   if not result['passed']:return dict(passed=False)
 return dict(passed=True,scope='sync-observe',core_cases=4,sync_loss_qualified=False)
