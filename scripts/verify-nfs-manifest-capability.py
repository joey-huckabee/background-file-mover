#!/usr/bin/env python3
"""Independently audit actual manifest discovery/withholding and SLES provenance."""
import argparse
import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import zlib
from nfs_manifest_capability import discover, held_manifest, manifest_data, sha
from nfs_mount_profile import covering, parse
from nfs_rpc import call as decode_call, reply as decode_reply


def held_bytes(state,obj):
    proof=held_manifest(state,obj)
    for item in state['held']:
        raw=bytes.fromhex(item['request']['payload_hex']);reply=bytes.fromhex(item['payload_hex'])
        assert sha(raw)==item['request']['sha256'] and sha(reply)==item['reply_sha256']
        assert decode_call(raw)==item['request']['decoded'] and decode_reply(reply)==item['reply']
    return proof


def scoped_buffer(trace,proof,target,obj):
    request=proof['write'];identity=proof['analysis']['filehandle_identities'][request['filehandle_sha256']]['identity']
    witnesses={}
    for m in proof['analysis']['metadata_matches']:
        witnesses.setdefault(m['mount_id'],set()).add(tuple(m['fsid']))
    matches=[]
    for index,event in enumerate(trace['events']):
        fd=event.get('descriptor')
        if not fd or event['syscall'] not in (1,18) or fd['path']!=target:continue
        if fd['inode']!=identity['fileid'] or witnesses.get(fd['mount_id'])!={tuple(identity['fsid'])}:continue
        position=event['args'][3] if event['syscall']==18 else fd['position']
        if position!=0 or event['result']!=int(obj['identity'].split(':')[3]):continue
        if event['enter_ns']>request['monotonic_ns'] or event.get('payload',{}).get('sha256')!=obj['sha256']:continue
        matches.append(index)
    assert matches,'no successful exact manifest buffer with scoped descriptor identity'
    return matches



def audit_loss(c,common):
    from nfs_manifest_recovery import validate_intent, validate_manifest_resend
    role=c['relay_role'];restarted=c['action']=='death-drop'
    assert c['wire']['forwarded']==c['wires'][role]['forwarded']
    trace=list(c['wires'][role]['trace'])
    if restarted:
        assert set(c['pre_restart_wires'])==set(c['wires'])
        for wire in c['pre_restart_wires'].values():common.wire_check(wire)
        before=c['pre_restart_wires'][role]
        assert c['pre_restart_receive_ids']==[v['receive_id'] for v in before['forwarded']]
        trace+=before['trace']
        assert c['coordinator_exit']!=0 and c['coordinator_exit_state']=='gone'
        assert c['worker_exit'] in ('gone','Z') and c['orphan_guard_probe']['exit_code']==73
        assert c['orphan_guard_probe']['worker_state']=='D'
        assert 'instance.lock' in c['worker_fds'] and 'jobs.sqlite' not in c['worker_fds']
        assert c['server_after_exit']==c['server_while_withheld']==c['server_before_republication']
        assert held_bytes(c['before_drop'],c['server_while_withheld'])==c['held_proof']
        assert c['restart_pause_point']=='manifest_link_rpc'
        assert c['restart_coordinator_pid']!=c['coordinator_pid']
        sec=dict(l.split(':',1) for l in c['restart_worker_security'].splitlines() if ':' in l)
        assert sec['Pid'].strip()==c['restart_paused_worker']['pid']!=c['paused_worker']['pid']
        assert sec['PPid'].strip()==c['restart_coordinator_pid'] and sec['Threads'].strip()=='1'
        assert sec['Uid'].split()==sec['Gid'].split()==['1000']*4 and sec['NoNewPrivs'].strip()=='1'
        assert all(int(sec[k],16)==0 for k in ('CapInh','CapPrm','CapEff'))
        assert '--internal-delivery-worker' in c['restart_paused_worker']['command']
        assert c['restart_status']['state']!='Committed' and c['restart_status']['details']['manifest_phase']==3
        assert c['restart_status']['details']['files'][0]['attempt']==1
        first=validate_intent(c['intent_before_restart'],c['server_while_withheld'],1)
        last=validate_intent(c['intent_after_stop'],c['server_final'],4)
        assert all(first[k]==last[k] for k in ('job_id','instance_id','bytes_base64','sha256'))
        assert first['object_identity'].split(':')[4]=='0'
        assert first['object_identity'].split(':')[:4]==last['object_identity'].split(':')[:4]
        assert c['final_coordinator_exit_state']=='gone'
    else:common.live_recovery(c)
    assert validate_manifest_resend(c,restarted)==c['resend_validation']
    if restarted:assert any(not item['session_replay'] for item in c['resend_validation']['successes'])
    records=c['wire']['forwarded'];assert len({v['receive_id'] for v in records})==len(records)
    for item in records:
        assert item['xid']==item['request']['decoded']['xid']==item['reply']['xid']
        if item['reply']['status']==0:
            assert [v['op'] for v in item['reply']['operations']]==[v['op'] for v in item['request']['decoded']['operations']]
        if item['receive_id'] in c['resend_validation']['scope']['selected_receive_ids']:
            assert item['connection'] not in {v['connection'] for v in c['settled']['dropped']}
            assert item['receive_id'] not in {v['receive_id'] for v in c['settled']['dropped']}
        request=bytes.fromhex(item['request']['payload_hex']);response=bytes.fromhex(item['payload_hex'])
        assert sha(request)==item['request']['sha256'] and decode_call(request)==item['request']['decoded']
        assert sha(response)==item['reply_sha256'] and decode_reply(response)==item['reply']
        calls=[v for v in trace if v['direction']=='call' and v['connection']==item['connection'] and v['sha256']==sha(request)]
        replies=[v for v in trace if v['direction']=='reply' and v['connection']==item['connection'] and v['sha256']==sha(response)]
        assert calls and replies and min(v['monotonic_ns'] for v in calls)<=min(v['monotonic_ns'] for v in replies)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('live',type=Path)
    parser.add_argument('--production-gate',type=Path,required=True)
    parser.add_argument('--qualification-gate',type=Path,required=True)
    parser.add_argument('--loss',action='store_true')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    def read(path):return json.loads(path.read_text(encoding='utf-8'))
    def save(name,value):(root/'docs'/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')
    helper=root/'scripts/verify-nfs-buffered-commit.py'
    spec=importlib.util.spec_from_file_location('payload_audit',helper)
    common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
    live=read(args.live/'report.json');auth=live['authorization']
    assert live['status']=='PASSED' and not live['cleanup_errors'] and live['rust_executed']
    assert live['glibc']=='glibc 2.22' and live['config']==read(root/'scripts/rust-platform.json')
    assert not live['production_nfs_enabled'] and not live['source_deletion_enabled']
    assert live['observer_capabilities']==['SYS_PTRACE','DAC_READ_SEARCH']
    client=dict(l.split(':',1) for l in live['client_security'].splitlines() if ':' in l)
    assert all(int(client[k],16)==((1<<21)|(1<<19)|(1<<2)) for k in ('CapPrm','CapEff','CapBnd'))
    assert int(client['CapInh'],16)==int(client['CapAmb'],16)==0 and client['NoNewPrivs'].strip()=='1'
    assert len(live['checks'])==43 and all(c['passed'] for c in live['checks'])
    assert auth['passed'] and auth['matrix']==('manifest-loss' if args.loss else 'manifest-capability') and auth['proof_tests']['passed']
    assert len(live['sources'])==(30 if args.loss else 28)
    if args.loss:assert auth['recovery_proof_tests']['passed']
    for name,item in live['sources'].items():
        raw=base64.b64decode(item['base64']);assert sha(raw)==item['sha256'] and raw==(root/'scripts'/name).read_bytes()
    for relay in auth['relays'].values():
        sec=dict(l.split(':',1) for l in relay['security'].splitlines() if ':' in l)
        assert sec['Uid'].split()==sec['Gid'].split()==['1000']*4 and sec['NoNewPrivs'].strip()=='1'
        assert all(int(sec[k],16)==0 for k in ('CapInh','CapPrm','CapEff'))
        assert not relay['ports_published'] and not relay['final_state']['armed'] and not relay['final_state']['errors']
    cases=auth['cases'];assert len(cases)==(16 if args.loss else 8)
    assert {(c['layout'],c['profile'],c['action']) for c in cases}=={
        (layout,profile,action) for layout in ('same-share','separate-shares')
        for profile in ('debug','release') for action in (('discovery','hold-release','live-drop','death-drop') if args.loss else ('discovery','hold-release'))}
    discoveries={};summaries=[]
    expected=sha(bytes(2097152)+b'0123456789abcdefg')
    for c in cases:
        assert c['passed'] and c['source_and_state_preserved'] and c['source_retained'] and c['service_reply_loss_tested']==c['action'].endswith('drop')
        assert c['point']=='publish' and c['scenario_id']==('SC-116' if c['action'].endswith('drop') else 'SC-115') and c['coordinator_pid'].isdigit()
        assert c['binary_sha256']==auth['gates']['qualification']['artifacts'][c['profile']]['sha256']
        assert c['filesystem_types'][:2]==['6969','6969'] and c['filesystem_types'][2]!='6969'
        assert c['root_identities_stable']
        mounts=[covering(parse(c['inventory']),c['config'][role+'_root']) for role in ('source','destination')]
        assert (mounts[0]==mounts[1])==(c['layout']=='same-share')
        assert all('noac' not in m['super'] and 'sync' not in m['super'] for m in mounts)
        assert all(c['config'][role+'_binding']['nfs_mount']['profile']=='NMP-41B' for role in ('source','destination'))
        sec=dict(l.split(':',1) for l in c['worker_security'].splitlines() if ':' in l)
        assert sec['Uid'].split()==sec['Gid'].split()==['1000']*4 and sec['NoNewPrivs'].strip()=='1'
        assert all(int(sec[k],16)==0 for k in ('CapInh','CapPrm','CapEff'))
        assert sec['Pid'].strip()==c['paused_worker']['pid'] and sec['PPid'].strip()==c['coordinator_pid'] and sec['Threads'].strip()=='1'
        assert '/tmp/qualification-'+c['profile'] in c['paused_worker']['command'] and '--internal-delivery-worker' in c['paused_worker']['command']
        assert c['target']==c['config']['destination_root']+'/1/.staging/COMMITTED.part'
        assert set(c['wires'])==({'source'} if c['layout']=='same-share' else {'source','destination'})
        for wire in c['wires'].values():common.wire_check(wire)
        final=c['server_final'];data=manifest_data(final,c['manifest']['submission_id'])
        assert 0<len(data)<=131072 and json.loads(data)==c['manifest'] and final['nfsd_threads']=='2'
        assert c['manifest']['submission_id']==c['committed']['details']['submission_id']
        assert c['source_identity_after']==c['original_source'][0] and c['original_source'][1].split()[0]==expected
        assert c['database_before']==c['database_after'] and c['enrollment_before']==c['enrollment_after']
        assert [v.split()[0] for v in c['hashes']]==[expected,expected]
        assert c['committed']['state']=='Committed' and c['committed']['details']['files'][0]['attempt']==1
        assert not c['committed']['details']['source_cleanup_enabled']
        assert c['accepted'][0]==c['replay'][0]==202 and c['accepted'][1]['job_id']==c['replay'][1]['job_id']=='1'
        assert c['accepted'][1]['source_paths_released'] and c['replay'][1]['source_paths_released']
        key=c['layout'],c['profile']
        if c['action']=='discovery':
            trace=c['trace'];assert trace['passed'] and not trace.get('cleanup_error')
            assert trace['pid']==int(c['paused_worker']['pid'])
            assert trace['expected_exit']=='supervised-delivery' and trace['exit_status'] in (0,9) and c['worker_exit'] in ('gone','Z')
            assert trace['event_limit']==8192 and len(trace['events'])<=8192 and trace['payload_limit']==8*1048576
            size=0
            for event in trace['events']:
                assert event['enter_ns']<=event['exit_ns'] and len(event['args'])==6
                if 'payload' in event:
                    p=event['payload'];raw=zlib.decompress(base64.b64decode(p['zlib_base64']))
                    assert sha(raw)==p['sha256'] and len(raw)==p['size']==event['args'][2]
                    assert event['syscall'] in (1,18) and len(raw)<=1048576
                    size+=len(raw)
            assert size==trace['payload_bytes']<=8*1048576
            clocks=c['clock_namespaces'];assert len(clocks)==(3 if c['layout']=='same-share' else 4)
            assert len(set(clocks.values()))==1 and all(v.startswith('time:[') for v in clocks.values())
            proof=discover(trace,c['wires'],c['target'],final);assert proof==c['discovery']
            scoped_buffer(trace,proof,c['target'],final)
            assert proof['analysis']['filehandle_identities'][proof['write']['filehandle_sha256']]['identity']['fileid']==int(final['identity'].split(':')[1])
            discoveries[key]=c
            summaries.append(dict(layout=c['layout'],profile=c['profile'],action=c['action'],write=proof['write'],
                commit_requests=proof['commit_requests'],commit_scope='Decoded requests on the attributed manifest handle in the captured window',unknown_calls=proof['analysis']['undecoded_calls']))
        else:
            assert key in discoveries,'healthy discovery must precede its control'
            original=discoveries[key];observed=original['discovery']['write']
            obj=c['server_while_withheld'];assert manifest_data(obj,c['manifest']['submission_id'])==data
            assert obj['nfsd_threads']=='2' and obj['identity'].split(':')[:2]==final['identity'].split(':')[:2]
            proof=held_bytes(c['held'],obj);assert held_bytes(c['before_release'],obj)==proof==c['held_proof']
            assert proof['requested_stable']==observed['operation']['stable'] and proof['committed']==observed['result']['committed']
            pending=c['pending'];args_=pending['syscall'].split();number=int(args_[0])
            assert number in {original['trace']['events'][i]['syscall'] for i in observed['descriptor_events']}
            assert number in (1,18,74,91) and int(args_[1],16)==pending['fd']
            if number==91:assert int(args_[2],16)==0o400
            assert pending['path']==c['target'] and pending['state']=='D'
            info=dict(l.split(':',1) for l in pending['fdinfo'].splitlines() if ':' in l)
            assert int(info['ino'])==int(obj['identity'].split(':')[1]) and int(info['mnt_id'])==int(mounts[1]['id'])
            assert c['health_seconds']<5 and c['during']['state']!='Committed' and c['during']['details']['condition']!='ReviewRequired'
            assert c['during']['details']['files'][0]['transfer_phase']=='Published' and c['final_absent_while_withheld']
            assert c['during']['details']['manifest_phase']==1
            assert c['held_replay'][0]==202 and c['held_replay'][1]['job_id']=='1' and c['held_replay'][1]['source_paths_released']
            settled=c['settled'];assert not settled['armed'] and not settled['errors']
            if c['action']=='hold-release':
                assert not settled['dropped'] and settled['released']==c['before_release']['held']
            else:
                assert not settled['released'] and settled['dropped']==c['before_release']['held']
                assert settled['connection_resets']
                audit_loss(c,common)

            role=c['relay_role'];wire=c['wires'][role]['trace']+c.get('pre_restart_wires',{}).get(role,{}).get('trace',[])
            for item in [*settled['released'],*settled['dropped']]:
                assert any(r['direction']=='call' and r['connection']==item['connection'] and r['sha256']==item['request']['sha256'] for r in wire)
                assert any(r['direction']=='reply' and r['connection']==item['connection'] and r['sha256']==item['reply_sha256'] for r in wire)
            summaries.append(dict(layout=c['layout'],profile=c['profile'],action=c['action'],pending_syscall=number,
                relay_role=role,proof=proof,manifest_phase_while_withheld=c['during']['details']['manifest_phase'],
                recovery=c.get('resend_validation'),orphan_guard_probe=c.get('orphan_guard_probe'),
                live_recovery_samples=c.get('live_recovery_samples')))
    assert len(auth['discoveries'])==4
    for item in auth['discoveries']:
        proof=discoveries[item['layout'],item['profile']]['discovery']
        assert item['write']==proof['write'] and item['commit_requests']==proof['commit_requests']
    controls=[]
    example=next(c for c in cases if c['action']=='hold-release')
    for label in ('unarmed','forwarded','reply_hash','request_hash','rehashed_reply_xid','rehashed_request_xid'):
        state=copy.deepcopy(example['held']);item=state['held'][0]
        if label=='unarmed':state['armed']=False
        elif label=='forwarded':state['forwarded']=state['held']
        elif label=='reply_hash':item['reply_sha256']='wrong'
        elif label=='request_hash':item['request']['sha256']='wrong'
        else:
            target=item if label=='rehashed_reply_xid' else item['request']
            raw=bytearray.fromhex(target['payload_hex']);raw[0]^=1;target['payload_hex']=raw.hex()
            if label=='rehashed_reply_xid':item['reply_sha256']=sha(raw);item['reply']=decode_reply(raw)
            else:target['sha256']=sha(raw);target['decoded']=decode_call(raw)
        try:held_bytes(state,example['server_while_withheld'])
        except (AssertionError,ValueError):controls.append(dict(name=label,passed=True))
        else:raise AssertionError('invalid held proof accepted: '+label)
    sample=next(c for c in cases if c['action']=='discovery')
    for label in ('buffer_foreign_inode','buffer_unwitnessed_mount','buffer_wrong_bytes','buffer_failed','buffer_wrong_position','buffer_after_rpc'):
        trace=copy.deepcopy(sample['trace']);proof=sample['discovery']
        indices=scoped_buffer(trace,proof,sample['target'],sample['server_final'])
        for index in indices:
            e=trace['events'][index]
            if label=='buffer_foreign_inode':e['descriptor']['inode']+=1
            elif label=='buffer_unwitnessed_mount':e['descriptor']['mount_id']='foreign'
            elif label=='buffer_wrong_bytes':e['payload']['sha256']='foreign'
            elif label=='buffer_failed':e['result']=-5
            elif label=='buffer_wrong_position':
                if e['syscall']==18:e['args'][3]=1
                else:e['descriptor']['position']=1
            else:e['enter_ns']=proof['write']['monotonic_ns']+1
        try:scoped_buffer(trace,proof,sample['target'],sample['server_final'])
        except AssertionError:controls.append(dict(name=label,passed=True))
        else:raise AssertionError('invalid scoped buffer accepted: '+label)
    if args.loss:
        from nfs_manifest_recovery import validate_intent, validate_manifest_resend
        sample=next(c for c in cases if c['action']=='live-drop')
        for label in ('missing_success','old_connection','changed_bytes','wrong_count','weak_stability','changed_verifier','missing_wire'):
            row=copy.deepcopy(sample)
            if label=='missing_success':row['wire']['forwarded']=[]
            elif label=='missing_wire':row['wires'][row['relay_role']]['trace']=[]
            else:
                item=next(v for v in row['wire']['forwarded'] if v['reply']['status']==0
                          and v['request']['decoded']['operations'][1]['filehandle_sha256']==row['resend_validation']['scope']['filehandle_sha256'])
                op=item['request']['decoded']['operations'][-1]
                reply=next(v for v in item['reply']['operations'] if v['op']==38)
                if label=='old_connection':item['connection']=row['settled']['dropped'][0]['connection']
                elif label=='changed_bytes':op['data_sha256']='wrong'
                elif label=='wrong_count':reply['count']+=1
                elif label=='weak_stability':reply['committed']=0
                else:reply['verifier_hex']='wrong'
            try:validate_manifest_resend(row)
            except AssertionError:controls.append(dict(name='loss_'+label,passed=True))
            else:raise AssertionError('invalid loss evidence accepted: '+label)
        sample=next(c for c in cases if c['action']=='death-drop')
        for label in ('copy_hash','recorded_phase','server_inode','server_bytes'):
            snapshot=copy.deepcopy(sample['intent_before_restart']);obj=copy.deepcopy(sample['server_while_withheld'])
            if label=='copy_hash':snapshot['files']['jobs.sqlite']['sha256']='wrong'
            elif label=='recorded_phase':snapshot['intent']['phase']=4
            elif label=='server_inode':
                parts=obj['identity'].split(':');parts[1]=str(int(parts[1])+1);obj['identity']=':'.join(parts)
            else:obj['base64']=base64.b64encode(b'wrong').decode()
            try:validate_intent(snapshot,obj,1)
            except AssertionError:controls.append(dict(name='intent_'+label,passed=True))
            else:raise AssertionError('invalid intent evidence accepted: '+label)
    current={p.relative_to(root/'rust').as_posix():p.read_bytes() for child in (root/'rust').iterdir()
             if child.name not in ('target','validation') for p in (child.rglob('*') if child.is_dir() else [child]) if p.is_file()}
    inputs=dict(live_run_id=live['run_id'],matrix='manifest-loss' if args.loss else 'manifest-capability',rust_input_count=len(current),
        rust_inputs={name:sha(data) for name,data in current.items()},case_analysis=summaries,gates={},
        proof_negative_controls=controls,python_regressions={})
    for name in ('test_nfs_rpc.py','test_nfs_io_analysis.py','test_nfs_manifest_capability.py',*(['test_nfs_manifest_recovery.py'] if args.loss else [])):
        tested=subprocess.run([sys.executable,str(root/'scripts'/name),'-v'],capture_output=True,text=True,timeout=20)
        assert tested.returncode==0;inputs['python_regressions'][name]=dict(passed=True,output=tested.stdout+tested.stderr)
    selector_flag='--manifest-loss' if args.loss else '--manifest-capability'
    selector=subprocess.run([sys.executable,str(root/'scripts/check-nfs-mount-profile.py'),selector_flag],capture_output=True,text=True,timeout=20)
    assert selector.returncode!=0 and selector_flag[2:]+' requires both gates' in selector.stderr and not selector.stdout
    inputs['selector_negative_control']=dict(passed=True,output=selector.stderr)
    gates={};count=0
    for mode,folder,expected_tests in (('production',args.production_gate,211),('qualification',args.qualification_gate,212)):
        gate=read(folder/'report.json')
        assert gate['status']=='PASSED' and not gate.get('cleanup_error') and gate['config']==live['config']
        assert gate['build_mode']==('production' if mode=='production' else 'nfs-qualification')
        assert len(gate['dependencies'])==42 and len(gate['audit_negative_controls'])==6
        archive=(folder/'source.tar.gz').read_bytes();assert sha(archive)==gate['source_sha256']
        with tarfile.open(folder/'source.tar.gz') as tar:assert {m.name:tar.extractfile(m).read() for m in tar if m.isfile()}==current
        used=auth['gates'][mode];prior_folder=root/'rust/validation'/used['run_id'];prior=read(prior_folder/'report.json')
        assert prior['status']=='PASSED' and not prior.get('cleanup_error') and prior['source_sha256']==used['source_sha256']
        assert sha((prior_folder/'source.tar.gz').read_bytes())==used['source_sha256']
        with tarfile.open(prior_folder/'source.tar.gz') as tar:assert {m.name:tar.extractfile(m).read() for m in tar if m.isfile()}==current
        for profile in ('debug','release'):
            item=gate['profiles'][profile];assert item['tests_passed']==expected_tests and len(item['artifacts'])==10
            assert [a['sha256'] for a in item['artifacts']]==[a['sha256'] for a in prior['profiles'][profile]['artifacts']]
            assert next(a for a in item['artifacts'] if not a['test'])['sha256']==used['artifacts'][profile]['sha256']
            for artifact in item['artifacts']:
                assert sha((folder/artifact['name']).read_bytes())==artifact['sha256'];count+=1
        gates[mode]=gate
        inputs['gates'][mode]=dict(run_id=gate['run_id'],source_sha256=gate['source_sha256'],
            source_archive_base64=base64.b64encode(archive).decode(),byte_identical_artifacts_to_live_gate=used['run_id'],artifact_count=20)
    if args.loss:
        initial_path=root/'docs/RUST-NFS-MANIFEST-LOSS-INITIAL-EVIDENCE.json'
        retained=read(initial_path);raw=zlib.decompress(base64.b64decode(retained['report_zlib_base64']))
        assert sha(raw)==retained['report_sha256']
        initial=json.loads(raw)
        assert initial['status']=='FAILED' and initial['run_id']=='mount-profile-20261020T012953Z-261a2261' and not initial['cleanup_errors']
        assert 'server_before_republication' in initial['traceback'] and len(initial['sources'])==30
        for item in initial['sources'].values():assert sha(base64.b64decode(item['base64']))==item['sha256']
        failed=initial['authorization']['cases'];assert len(failed)==7 and all(v['passed'] for v in failed[:-1]) and not failed[-1]['passed']
        case=failed[-1];before=case['server_while_withheld'];after=case['server_before_republication']
        assert before['base64']==after['base64'] and before['sha256']==after['sha256']
        assert before['identity'].split(':')[:2]==after['identity'].split(':')[:2]
        assert before['identity'].split(':')[2]=='1' and after['identity'].split(':')[2]=='2'
        assert case['worker_exit'] in ('gone','Z') and case['coordinator_exit_state'] in ('gone','Z')
        assert held_bytes(case['held'],before)==case['held_proof']
        validate_intent(case['intent_before_restart'],before,1)
        inputs['initial_failed_acquisition']=dict(run_id=initial['run_id'],report_sha256=sha(raw),raw_bytes=len(raw),
            retained_file=initial_path.name,source_snapshots=30,passed_cases=6,cleanup_errors=[],
            cause='Fixture selected manifest_link after durable LINK; corrected to existing manifest_link_rpc before LINK and fully reacquired.')
    if args.loss:
        retained=read(root/'docs/RUST-NFS-MANIFEST-LOSS-REACQUISITION-EVIDENCE.json')
        raw=zlib.decompress(base64.b64decode(retained['report_zlib_base64']));assert sha(raw)==retained['report_sha256']
        retry=json.loads(raw)
        assert retry['status']=='FAILED' and retry['run_id']=='mount-profile-20261020T014416Z-9ffaf0f3' and not retry['cleanup_errors']
        assert 'payload_resends' in retry['traceback'] and len(retry['sources'])==30
        for item in retry['sources'].values():assert sha(base64.b64decode(item['base64']))==item['sha256']
        failed=retry['authorization']['cases'];assert len(failed)==7 and all(v['passed'] for v in failed[:-1]) and not failed[-1]['passed']
        case=failed[-1]
        assert case['recovered_status']['state']=='Committed' and case['recovered_status']['details']['files'][0]['attempt']==1
        assert case['restart_status']['details']['manifest_phase']==3
        assert case['server_before_republication']==case['server_while_withheld']
        proof=validate_manifest_resend(case,True)
        assert any(item['operations']==[53,22,38,9] for item in proof['successes'])
        for wire in [*case['wires'].values(),*case['pre_restart_wires'].values()]:common.wire_check(wire)
        inputs['second_failed_acquisition']=dict(run_id=retry['run_id'],report_sha256=sha(raw),raw_bytes=len(raw),
            retained_file='RUST-NFS-MANIFEST-LOSS-REACQUISITION-EVIDENCE.json',source_snapshots=30,passed_cases=6,cleanup_errors=[],
            recovery_rpc_proof=proof,cause='Service reached Committed; evidence selector rejected observed post-restart WRITE+GETATTR compound. Final selector explicitly validates both observed shapes and preserves every operation/raw byte.')
    inventory=read(args.live/'post-run-inventory.json')
    assert not inventory['default']['containers'] and not inventory['rootful']['containers']
    assert set(inventory['rootful']['volumes'])=={'file-mover-rustup-1-99','file-mover-cargo-registry'} and inventory['rootful']['networks']==['podman']
    inputs.update(post_run_inventory=inventory,verified_elf_count=count,source_snapshot_count=len(live['sources']),all_driver_snapshots_match_current=True)
    for key,path in (('verifier',Path(__file__)),('shared_wire_auditor',helper)):
        data=path.read_bytes();inputs[key]=dict(sha256=sha(data),base64=base64.b64encode(data).decode())
    compressor=zlib.compressobj(9);hasher=hashlib.sha256();chunks=[]
    with (args.live/'report.json').open('rb') as source:
        while block:=source.read(1048576):hasher.update(block);chunks.append(compressor.compress(block))
    chunks.append(compressor.flush())
    prefix='RUST-NFS-MANIFEST-LOSS' if args.loss else 'RUST-NFS-MANIFEST-CAPABILITY'
    save(prefix+'-EVIDENCE.json',dict(format='zlib-base64-json',report_sha256=hasher.hexdigest(),report_zlib_base64=base64.b64encode(b''.join(chunks)).decode()))
    save(prefix+'-INPUT-EVIDENCE.json',inputs)
    save('RUST-SLES-EVIDENCE.json',gates['production']);save('RUST-SLES-QUALIFICATION-EVIDENCE.json',gates['qualification'])
    print(json.dumps(dict(run_id=live['run_id'],worker_discoveries=4,hold_release_controls=4,loss_recoveries=8 if args.loss else 0,verified_elf_count=count,driver_snapshots=len(live['sources']),cleanup_errors=[])))


if __name__=='__main__':main()
