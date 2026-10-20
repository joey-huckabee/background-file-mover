#!/usr/bin/env python3
"""Independent retained-proof and exact-build audit for claim controls/loss recovery."""
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
from nfs_claim_capability import claim_proof
from nfs_mount_profile import covering, parse
from nfs_rpc import call, reply, Xdr
from nfs_claim_recovery import validate_claim_resend, raw_item


def sha(data): return hashlib.sha256(data).hexdigest()


def sequence_result_offset(item):
    # RFC 8881 18.46.2-3: successful SEQUENCE echoes session/sequence/slot.
    raw_item(item);x=Xdr(bytes.fromhex(item['payload_hex']))
    assert [x.uint() for _ in range(3)]==[item['xid'],1,0]
    x.uint();x.opaque();assert x.uint()==0
    assert x.uint()==item['reply']['status'];x.opaque();assert x.uint()>=1
    assert x.uint()==53 and x.uint()==0
    return x.offset


def sequence_echo(item):
    offset=sequence_result_offset(item)
    data=bytes.fromhex(item['payload_hex']);request=bytes.fromhex(item['request']['decoded']['operations'][0]['sequence_hex'])
    assert data[offset:offset+24]==request[:24]


def full_retry_key(item):
    raw_item(item)
    raw=bytearray.fromhex(item['request']['payload_hex'])
    seq=bytes.fromhex(item['request']['decoded']['operations'][0]['sequence_hex'])
    assert len(seq)==32 and raw.count(seq)==1
    position=raw.find(seq);assert position>=24
    raw[:4]=bytes(4)  # RPC transaction ID is distinct from namespace session identity.
    raw[position+24:position+28]=bytes(4)  # highest_slotid hint only
    return bytes(raw)


def audit_live_bytes(c):
    original=c['settled']['dropped'][0];expected=full_retry_key(original)
    selected=c['wires'][c['relay_role']]['forwarded'];assert selected
    assert all(full_retry_key(item)==expected for item in selected)


def audit_loss(c):
    action=c['action'];assert action in ('live-drop','death-drop')
    assert c['settled']['dropped']==c['before_release']['held'] and not c['settled']['released']
    assert c['settled']['connection_resets']
    for item in c['settled']['dropped']:raw_item(item)
    samples=c['custody_recovery_samples'];assert samples and len(samples)<=18
    assert samples[-1]['replay']==c['confirmed_custody']
    for v in samples:
        assert v['coordinator_pid']==c.get('restart_coordinator_pid',c['coordinator_pid'])
        assert v['health_code']==v['status'][0]==200 and v['health_seconds']<5 and v['status_seconds']<5 and v['replay_seconds']<15
        assert v['status'][1]['details']['condition']!='ReviewRequired' and not v['status'][1]['details']['source_cleanup_enabled']
        response=v['replay']
        if response[0]==202:assert response[1]['source_paths_released'] and response[1]['job_id']=='1'
        else:
            assert response[0]==503 and response[1]['retryable'] and not response[1]['source_paths_released']
            assert response[1]['error'] in ('handoff_pending','service_busy')
    if action=='live-drop':
        assert 'restart_coordinator_pid' not in c and validate_claim_resend(c)==c['resend_validation']
        audit_live_bytes(c)
    else:
        assert c['dead_coordinator_exit']!=0 and c['dead_coordinator_exit_state']=='gone'
        assert c['orphan_guard']['exit_code']==73 and c['orphan_guard']['state']=='D'
        assert 'instance.lock' in c['worker_fds'] and 'jobs.sqlite' not in c['worker_fds']
        assert c['orphan_status']['exit_code']==2 and c['orphan_status']['seconds']<5 and c['orphan_status']['snapshot']['phase']=='OwnerUnavailable'
        assert c['contender_exit']!=0 and 'local instance or surviving worker already owns state' in c['contender_diagnostic']
        assert c['epoch_after_contender']==c['original_epoch'] and c['original_epoch']['group']==int(c['coordinator_pid'])
        assert c['old_worker_exit'] in ('gone','Z') and c['restart_coordinator_pid']!=c['coordinator_pid']
        assert c['server_after_old_exit']==c['server_while_withheld']
        assert claim_proof(c['before_drop'],c['operation'],c['server_before_submission'],c['server_after_old_exit'])==c['proof']
        assert set(c['pre_restart_wires'])==set(c['wires'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('live', type=Path)
    parser.add_argument('--production-gate', type=Path, required=True)
    parser.add_argument('--qualification-gate', type=Path, required=True)
    parser.add_argument('--loss',action='store_true')
    args = parser.parse_args(); root = Path(__file__).resolve().parents[1]
    def read(path): return json.loads(path.read_text(encoding='utf-8'))
    def save(name,value): (root/'docs'/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')
    helper = root/'scripts/verify-nfs-buffered-commit.py'
    spec = importlib.util.spec_from_file_location('wire_audit',helper)
    common = importlib.util.module_from_spec(spec); spec.loader.exec_module(common)
    live = read(args.live/'report.json'); auth = live['authorization']
    assert live['status']=='PASSED' and not live['cleanup_errors'] and live['rust_executed']
    assert live['glibc']=='glibc 2.22' and live['config']==read(root/'scripts/rust-platform.json')
    assert not live['production_nfs_enabled'] and not live['source_deletion_enabled']
    assert live['observer_capabilities']==['SYS_PTRACE','DAC_READ_SEARCH']
    sec=dict(l.split(':',1) for l in live['client_security'].splitlines() if ':' in l)
    assert all(int(sec[k],16)==((1<<21)|(1<<19)|(1<<2)) for k in ('CapPrm','CapEff','CapBnd'))
    assert sec['NoNewPrivs'].strip()=='1' and int(sec['CapInh'],16)==int(sec['CapAmb'],16)==0
    assert len(live['checks'])==43 and all(c['passed'] for c in live['checks'])
    assert auth['passed'] and auth['matrix']==('claim-loss' if args.loss else 'claim-capability') and len(live['sources'])==(30 if args.loss else 28)
    for name,item in live['sources'].items():
        data=base64.b64decode(item['base64'],validate=True)
        assert sha(data)==item['sha256'] and data==(root/'scripts'/name).read_bytes()
    for relay in auth['relays'].values():
        sec=dict(l.split(':',1) for l in relay['security'].splitlines() if ':' in l)
        assert sec['Uid'].split()==sec['Gid'].split()==['1000']*4 and sec['NoNewPrivs'].strip()=='1'
        assert all(int(sec[k],16)==0 for k in ('CapInh','CapPrm','CapEff'))
        assert not relay['ports_published'] and not relay['final_state']['armed'] and not relay['final_state']['errors']
    cases=auth['cases']; assert len(cases)==(24 if args.loss else 8)
    assert {(c['layout'],c['profile'],c['operation'],c.get('action','hold-release')) for c in cases}=={
        (layout,profile,operation,action) for layout in ('same-share','separate-shares') for profile in ('debug','release') for operation in (11,28)
        for action in (('hold-release','live-drop','death-drop') if args.loss else ('hold-release',))}
    expected=sha(bytes(2097152)+b'0123456789abcdefg'); summaries=[]; controls=[]
    for c in cases:
        op=c['operation'];action=c.get('action','hold-release');fault=action.endswith('drop')
        assert c['passed'] and c['scenario_id']==('SC-118' if fault else 'SC-117') and c['service_reply_loss_tested']==fault
        assert c['point']==('claim_link_rpc' if op==11 else 'claim_unlink_rpc')
        assert c['binary_sha256']==auth['gates']['qualification']['artifacts'][c['profile']]['sha256']
        assert c['filesystem_types'][:2]==['6969','6969'] and c['filesystem_types'][2]!='6969'
        mounts=[covering(parse(c['inventory']),c['config'][role+'_root']) for role in ('source','destination')]
        assert (mounts[0]==mounts[1])==(c['layout']=='same-share')
        assert all('noac' not in m['super'] and 'sync' not in m['super'] for m in mounts)
        assert all(c['config'][role+'_binding']['nfs_mount']['profile']=='NMP-41B' for role in ('source','destination'))
        sec=dict(l.split(':',1) for l in c['worker_security'].splitlines() if ':' in l)
        assert sec['Uid'].split()==sec['Gid'].split()==['1000']*4 and sec['NoNewPrivs'].strip()=='1'
        assert sec['Pid'].strip()==c['paused_worker']['pid'] and sec['PPid'].strip()==c['coordinator_pid'] and sec['Threads'].strip()=='1'
        assert all(int(sec[k],16)==0 for k in ('CapInh','CapPrm','CapEff'))
        assert '--internal-claim-worker' in c['paused_worker']['command']
        assert c['pending']['state']=='D' and c['nfsd_threads']=='2' and c['destination_absent']
        words=c['pending']['syscall'].split(); assert len(words)==9 and int(words[0])==(265 if op==11 else 263)
        assert c['pending']['parent']==c['config']['source_root']+'/current/nested'
        fields=dict(l.split(':',1) for l in c['pending']['fdinfo'].splitlines() if ':' in l)
        assert fields['ino'].strip()==c['server_parent_inode'] and int(fields['mnt_id'])==int(mounts[0]['id'])
        if op==11:
            assert int(words[5],16)==0 and c['pending']['new_parent']==c['config']['source_root']+'/.file-mover/1-0'
            fields=dict(l.split(':',1) for l in c['pending']['new_fdinfo'].splitlines() if ':' in l)
            assert fields['ino'].strip()==c['server_new_parent_inode'] and int(fields['mnt_id'])==int(mounts[0]['id'])
        else: assert int(words[3],16)==0
        proof=claim_proof(c['held'],op,c['server_before_submission'],c['server_while_withheld'])
        assert proof==c['proof']==claim_proof(c['before_release'],op,c['server_before_submission'],c['server_while_withheld'])
        assert not c['settled']['armed'] and not c['settled']['errors']
        if fault:audit_loss(c)
        else:
            assert not c['settled']['dropped'] and c['settled']['released']==c['before_release']['held']
        assert set(c['wires'])==({'source'} if c['layout']=='same-share' else {'source','destination'})
        for wire in [*c['wires'].values(),*c.get('pre_restart_wires',{}).values()]:common.wire_check(wire)
        for role,state in c['wires'].items():
            earlier=c.get('pre_restart_wires',{}).get(role,{})
            joined=state['trace']+earlier.get('trace',[])
            seen={}
            for record in [*state['forwarded'],*earlier.get('forwarded',[])]:
                raw_item(record)
                if record['reply']['operations'][0]==dict(op=53,status=0):sequence_echo(record)
                if record['receive_id'] in seen:assert record==seen[record['receive_id']]
                seen[record['receive_id']]=record
                for direction,digest in (('call',record['request']['sha256']),('reply',record['reply_sha256'])):
                    assert any(v['direction']==direction and v['connection']==record['connection'] and v['xid']==record['xid'] and v['sha256']==digest for v in joined)
        sequence_echo(c['held']['held'][0])
        item=c['held']['held'][0]; wire=c['wires'][c['relay_role']]['trace']+c.get('pre_restart_wires',{}).get(c['relay_role'],{}).get('trace',[])
        matched={}
        for direction,hash_ in (('call',item['request']['sha256']),('reply',item['reply_sha256'])):
            rows=[v for v in wire if v['direction']==direction and v['sha256']==hash_ and v['connection']==item['connection'] and v['xid']==item['xid']]
            assert len(rows)==1; matched[direction]=rows[0]
        assert matched['call']['monotonic_ns']<=matched['reply']['monotonic_ns']
        # Require protocol FH setup, preserving every operation in the raw compound.
        ops=item['request']['decoded']['operations']; selected=next(i for i,o in enumerate(ops) if o['op']==op)
        assert sum(o['op'] in (11,28) for o in ops)==1
        assert ops[selected-1]['op']==22
        if op==11: assert any(o['op']==32 for o in ops[:selected])
        assert c['health']['response'][0]==200 and c['health']['seconds']<5
        status=c['during']['response']; assert status[0]==200 and c['during']['seconds']<5
        assert status[1]['state']=='Accepted' and not status[1]['source_paths_released'] and not status[1]['details']['source_cleanup_enabled']
        for response in (c['initial_submission'],c['held_replay']['response']):
            assert response[0]==503 and response[1]['retryable'] and not response[1]['source_paths_released']
            assert response[1]['error'] in ('handoff_pending','service_busy')
        assert c['held_replay']['seconds']<15
        assert c['confirmed_custody'][0]==202 and c['confirmed_custody'][1]['job_id']=='1' and c['confirmed_custody'][1]['source_paths_released']
        assert c['producer_reuse_after_202'] and c['source_retained'] and c['root_identities_stable']
        assert c['database_before']==c['database_after'] and c['enrollment_before']==c['enrollment_after']
        assert c['server_before_submission']['old']['sha256']==expected
        after=c['server_after']['final']; assert after['links']==1
        assert all(after[k]==c['server_before_submission']['old'][k] for k in ('device','inode','size','sha256'))
        assert [v.split()[0] for v in c['hashes']]==[expected,expected]
        assert c['committed']['state']=='Committed' and c['committed']['details']['files'][0]['attempt']==1
        assert not c['committed']['details']['source_cleanup_enabled'] and c['coordinator_exit_state']=='gone'
        assert c['manifest']['job_id']=='1' and c['manifest']['files'][0]['sha256']==expected
        summaries.append(dict(layout=c['layout'],profile=c['profile'],action=action,relay_role=c['relay_role'],recovery=c.get('resend_validation'),full_request_bytes_checked=action=='live-drop',**proof))
    for c in (cases[0],cases[1]):
        for name in ('reply_hash','request_hash','inode','bytes','unarmed','forwarded','name','xid','rehashed_name','rehashed_reply_xid'):
            state=copy.deepcopy(c['held']); before=copy.deepcopy(c['server_before_submission']); after=copy.deepcopy(c['server_while_withheld']); item=state['held'][0]
            if name=='reply_hash':item['reply_sha256']='wrong'
            elif name=='request_hash':item['request']['sha256']='wrong'
            elif name=='inode':after['final']['inode']+=1
            elif name=='bytes':after['final']['sha256']='wrong'
            elif name=='unarmed':state['armed']=False
            elif name=='forwarded':state['forwarded']=[item]
            elif name=='name':item['request']['decoded']['operations'][-1]['name']='wrong'
            elif name=='xid':item['xid']+=1
            elif name=='rehashed_name':
                data=bytes.fromhex(item['request']['payload_hex']).replace(b'data',b'evil',1)
                item['request'].update(payload_hex=data.hex(),sha256=sha(data),decoded=call(data))
            else:
                data=bytearray.fromhex(item['payload_hex']);data[0]^=1
                item.update(payload_hex=data.hex(),reply_sha256=sha(data),reply=reply(data))
            try:claim_proof(state,c['operation'],before,after)
            except (AssertionError,ValueError):controls.append(dict(operation=c['operation'],name=name,passed=True))
            else:raise AssertionError('invalid proof accepted: '+name)
    if args.loss:
        samples=[next(c for c in cases if c['action']=='live-drop' and c['operation']==op) for op in (11,28)]
        for c in samples:
            for label in ('missing_success','same_connection','same_receive','missing_trace','reply_hash','wrong_name','wrong_session','released'):
                row=copy.deepcopy({k:c[k] for k in ('settled','wires','relay_role')});wire=row['wires'][row['relay_role']];item=wire['forwarded'][0]
                if label=='missing_success':wire['forwarded']=[]
                elif label=='same_connection':item['connection']=row['settled']['dropped'][0]['connection']
                elif label=='same_receive':item['receive_id']=row['settled']['dropped'][0]['receive_id']
                elif label=='missing_trace':wire['trace']=[]
                elif label=='reply_hash':item['reply_sha256']='wrong'
                elif label=='released':row['settled']['released']=row['settled']['dropped']
                else:
                    data=bytearray.fromhex(item['request']['payload_hex'])
                    if label=='wrong_name':data=data.replace(b'data',b'evil',1)
                    else:
                        seq=bytes.fromhex(item['request']['decoded']['operations'][0]['sequence_hex']);offset=data.find(seq);assert offset>=0;data[offset]^=1
                    item['request'].update(payload_hex=data.hex(),sha256=sha(data),decoded=call(data))
                try:validate_claim_resend(row)
                except (AssertionError,ValueError):controls.append(dict(operation=c['operation'],name='loss_'+label,passed=True))
                else:raise AssertionError('invalid namespace replay accepted: '+label)
        row=copy.deepcopy(next(c for c in cases if c['action']=='live-drop' and c['operation']==11))
        item=row['wires'][row['relay_role']]['forwarded'][0]
        data=bytearray.fromhex(item['request']['payload_hex']);data[-1]^=1
        decoded=call(data);assert decoded==item['request']['decoded'], 'control must target a field omitted by the summary decoder'
        item['request'].update(payload_hex=data.hex(),sha256=sha(data),decoded=decoded)
        try:audit_live_bytes(row)
        except AssertionError:controls.append(dict(name='loss_changed_unexposed_getattr_bitmap',passed=True))
        else:raise AssertionError('changed metadata operation bytes accepted')
        sample=next(c for c in cases if c['action']=='live-drop')
        item=copy.deepcopy(sample['wires'][sample['relay_role']]['forwarded'][0])
        offset=sequence_result_offset(item);data=bytearray.fromhex(item['payload_hex']);data[offset]^=1
        decoded=reply(data);assert decoded==item['reply']
        item.update(payload_hex=data.hex(),reply_sha256=sha(data),reply=decoded)
        try:sequence_echo(item)
        except AssertionError:controls.append(dict(name='loss_changed_unexposed_reply_session',passed=True))
        else:raise AssertionError('wrong echoed session accepted')
        sample=next(c for c in cases if c['action']=='death-drop')
        for label in ('worker_alive','guard_free','changed_epoch','changed_server','same_coordinator'):
            row=copy.deepcopy(sample)
            if label=='worker_alive':row['old_worker_exit']='D'
            elif label=='guard_free':row['orphan_guard']['exit_code']=0
            elif label=='changed_epoch':row['epoch_after_contender']['group']+=1
            elif label=='changed_server':row['server_after_old_exit']['final']['inode']+=1
            else:row['restart_coordinator_pid']=row['coordinator_pid']
            try:audit_loss(row)
            except AssertionError:controls.append(dict(name='death_'+label,passed=True))
            else:raise AssertionError('invalid death evidence accepted: '+label)
    current={p.relative_to(root/'rust').as_posix():p.read_bytes() for child in (root/'rust').iterdir()
             if child.name not in ('target','validation') for p in (child.rglob('*') if child.is_dir() else [child]) if p.is_file()}
    assert len(current)==62
    inputs=dict(live_run_id=live['run_id'],matrix='claim-loss' if args.loss else 'claim-capability',rust_input_count=len(current),
        rust_inputs={name:sha(data) for name,data in current.items()},case_analysis=summaries,gates={},
        proof_negative_controls=controls,python_regressions={})
    for name in ('test_nfs_rpc.py','test_nfs_claim_capability.py',*(['test_nfs_claim_recovery.py'] if args.loss else [])):
        tested=subprocess.run([sys.executable,str(root/'scripts'/name),'-v'],capture_output=True,text=True,timeout=20)
        assert tested.returncode==0; inputs['python_regressions'][name]=dict(passed=True,output=tested.stdout+tested.stderr)
    selector_flag='--claim-loss' if args.loss else '--claim-capability'
    selector=subprocess.run([sys.executable,str(root/'scripts/check-nfs-mount-profile.py'),selector_flag],capture_output=True,text=True,timeout=20)
    assert selector.returncode!=0 and selector_flag[2:]+' requires both gates' in selector.stderr and not selector.stdout
    inputs['selector_negative_control']=dict(passed=True,output=selector.stderr)
    gate_helper=root/'scripts/check-rust-sles.py'
    spec=importlib.util.spec_from_file_location('sles_audit',gate_helper)
    gate_auditor=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate_auditor)
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
                data=(folder/artifact['name']).read_bytes()
                assert sha(data)==artifact['sha256'] and data==(prior_folder/artifact['name']).read_bytes()
                assert gate_auditor.audit((folder/(artifact['name']+'.elf')).read_text(encoding='utf-8'))==artifact['elf']
                count+=1
        gates[mode]=gate
        inputs['gates'][mode]=dict(run_id=gate['run_id'],source_sha256=gate['source_sha256'],
            source_archive_base64=base64.b64encode(archive).decode(),byte_identical_artifacts_to_live_gate=used['run_id'],artifact_count=20)

    inventory=read(args.live/'post-run-inventory.json')
    assert not inventory['default']['containers'] and not inventory['rootful']['containers']
    assert set(inventory['rootful']['volumes'])=={'file-mover-rustup-1-99','file-mover-cargo-registry'} and inventory['rootful']['networks']==['podman']
    baseline=read(root/'docs/RUST-NFS-MANIFEST-LOSS-INPUT-EVIDENCE.json')['post_run_inventory']
    assert set(inventory['default']['volumes'])==set(baseline['default']['volumes'])
    assert sorted(inventory['default']['volume_metadata'],key=lambda v:v['Name'])==sorted(baseline['default']['volume_metadata'],key=lambda v:v['Name'])
    inputs.update(post_run_inventory=inventory,verified_elf_count=count,source_snapshot_count=len(live['sources']),all_driver_snapshots_match_current=True)
    for key,path in (('verifier',Path(__file__)),('shared_wire_auditor',helper),('gate_auditor',gate_helper)):
        data=path.read_bytes();inputs[key]=dict(sha256=sha(data),base64=base64.b64encode(data).decode())
    raw=(args.live/'report.json').read_bytes()
    prefix='RUST-NFS-CLAIM-LOSS' if args.loss else 'RUST-NFS-CLAIM-CAPABILITY'
    save(prefix+'-EVIDENCE.json',dict(format='zlib-base64-json',report_sha256=sha(raw),report_zlib_base64=base64.b64encode(zlib.compress(raw,9)).decode()))
    save(prefix+'-INPUT-EVIDENCE.json',inputs)
    save('RUST-SLES-EVIDENCE.json',gates['production']); save('RUST-SLES-QUALIFICATION-EVIDENCE.json',gates['qualification'])
    print(json.dumps(dict(run_id=live['run_id'],hold_release_controls=8,loss_recoveries=16 if args.loss else 0,verified_elf_count=count,driver_snapshots=len(live['sources']),cleanup_errors=[])))



if __name__=='__main__':main()
