#!/usr/bin/env python3
"""Audit actual source-claim fsync boundaries, raw RPC attribution and compatibility."""
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
from nfs_mount_profile import covering, parse
from nfs_rpc import call, reply


def sha(data):return hashlib.sha256(data).hexdigest()


def load_module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def analyze(c,inventory):
    expected=sha(bytes(2*1048576)+b'0123456789abcdefg')
    assert c['passed'] and c['scenario_id']=='SC-133' and c['original_state_preserved'] and c['root_identities_stable'] and c['source_retained']
    assert not c['production'] and c['point']=='claim_link_rpc'
    assert c['handoff']['job_id']==c['replay']['job_id']=='1' and c['handoff']['source_paths_released'] and c['replay']['source_paths_released']
    assert c['local_before']==c['local_after'] and c['enrollment_before']==c['enrollment_after']
    assert c['status_before']==c['status_during'] and c['status_before']['state']=='Accepted'
    assert c['guard_exit']==73 and c['epoch_before']==c['epoch_during'] and c['epoch_before']['group']==int(c['coordinator_pid'])
    assert c['worker_pid']==c['paused_worker']['pid'] and '--internal-claim-worker' in c['paused_worker']['command']
    assert len(set(c['clock_namespaces'].values()))==1 and c['entry_worker_state'] in ('t','T')
    security=dict(x.split(':',1) for x in c['worker_security'].splitlines() if ':' in x)
    assert security['Uid'].split()==security['Gid'].split()==['1000']*4 and security['NoNewPrivs'].strip()=='1'
    assert all(int(security[k],16)==0 for k in ('CapInh','CapPrm','CapEff'))
    assert c['health_seconds']<5 and c['worker_exit'] in ('gone','Z')
    custody=c['custody_before'];assert custody==c['custody_exit']
    assert custody['delivery_absent'] and custody['original']==custody['private']
    assert custody['private']['sha256']==expected and custody['private']['identity'].split(':')[2:]==['2','2097169']
    old=custody['private']['identity'].split(':')
    assert c['private_after']==dict(identity=':'.join(old[:2]+['1',old[3]]),sha256=expected)
    assert c['original_absent_at_202'] and c['producer_after']=='next recording'
    assert c['exit_release_ns']<c['handoff_ns']<c['source_reuse_ns']
    pending=c['original_request_before_release'];assert not pending.startswith('HTTP/1.1 202')
    if pending.startswith('HTTP/'):
        head,body=pending.replace('\r\n','\n').split('\n\n',1);body=json.loads(body)
        assert int(head.split()[1])==503 and body['retryable'] and not body['source_paths_released']
    raw=c['original_request']['raw']
    if raw.startswith('HTTP/'):
        head,body=raw.replace('\r\n','\n').split('\n\n',1);code=int(head.split()[1]);body=json.loads(body)
        assert c['original_request']['parsed']==[code,body]
        if code==202:assert body['job_id']=='1' and body['source_paths_released']
        else:assert code==503 and body['retryable'] and not body['source_paths_released']
    assert c['retry_responses'][-1]==[202,c['handoff']]
    for code,body in c['retry_responses'][:-1]:assert code==503 and body['retryable'] and not body['source_paths_released']
    assert c['filesystem_types'][:2]==['6969','6969'] and c['filesystem_types'][2]!='6969'
    mounts=[covering(parse(inventory),c['config'][role+'_root']) for role in ('source','destination')]
    assert all(m['device'].startswith('0:') and m['filesystem']=='nfs4' for m in mounts)
    devices=[m['device'].split(':')[1] for m in mounts]+[c['local_before'].splitlines()[0].split(':')[0]]
    assert len(set(devices))==3
    before,after=c['before_server'],c['after_server']
    assert all(before[k]==after[k] for k in ('container','pid','started_at','image','mounts','address','boot_id','netns')) and before['threads']==after['threads']=='2'
    trace=c['trace'];assert trace['passed'] and not trace.get('cleanup_error') and trace['pid']==int(c['worker_pid']) and trace['exit_status']==0 and trace['expected_exit']=='zero'
    assert trace['syncs']==[e for e in trace['events'] if e['syscall'] in (74,75)] and all(e['result']==0 for e in trace['syncs'])
    gate=trace['gate'];assert gate['entry']==c['entry'] and gate['exit']==c['exit']
    target=c['config']['source_root']+'/.file-mover/1-0'+('/data' if c['phase']=='file' else '')
    assert gate['path']==target
    selected=[e for e in trace['syncs'] if e['path']==target and e['fd']==c['entry']['fd'] and e['enter_ns']==c['exit']['enter_ns']]
    assert len(selected)==1;e=selected[0]
    assert e['syscall']==c['entry']['syscall']==74 and e['args']==c['entry']['args'] and e['args'][0]==c['entry']['fd'] and e['descriptor']['filesystem']=='nfs4'
    assert e['descriptor']==c['entry']['descriptor'] and e['result']==c['exit']['result']==0 and e['exit_ns']==c['exit']['exit_ns']
    assert {k:v for k,v in c['exit'].items() if k!='observed_ns'}==e
    assert c['entry']['observed_ns']<c['entry_release_ns']<=e['enter_ns']<=e['exit_ns']<=c['exit']['observed_ns']<c['exit_release_ns']
    private_parent=c['config']['source_root']+'/.file-mover/1-0';original_parent=c['config']['source_root']+'/current/nested'
    links=[x for x in trace['events'] if x['syscall']==265 and x.get('pathname')=='data.bin' and x.get('second_pathname')=='data']
    assert len(links)==1 and links[0]['result']==0 and links[0]['exit_ns']<c['entry']['observed_ns']
    assert links[0]['descriptor']['path']==original_parent and links[0]['second_directory']['path']==private_parent
    if c['phase']=='file':assert e['inode']==int(custody['private']['identity'].split(':')[1])
    else:assert c['phase']=='directory' and e['inode']==links[0]['second_directory']['inode']
    unlinks=[x for x in trace['events'] if x['syscall']==263 and x.get('pathname')=='data.bin'];assert len(unlinks)==1 and unlinks[0]['result']==0
    assert unlinks[0]['descriptor']['path']==original_parent and unlinks[0]['enter_ns']>c['exit_release_ns']
    assert [x['path'] for x in trace['syncs']]==[private_parent+'/data',private_parent,original_parent,private_parent+'/data',private_parent,original_parent,c['config']['source_root']+'/.file-mover']

    if c['mode']=='nfsd-stopped':
        assert c['stopped_server']['threads']=='0' and c['custody_stopped']==custody
        assert all(c['stopped_server'][k]==before[k] for k in ('container','pid','started_at','boot_id','netns'))
        if c['outcome']=='completed_while_nfsd_stopped':
            assert c['blocked_sync'] is None and c['exit_before_restore']==c['exit'] and e['exit_ns']<c['restore_started_ns']
        else:
            assert c['outcome']=='blocked_sync' and c['blocked_sync']['state']=='D' and c['exit_before_restore'] is None
            raw=c['blocked_sync']['syscall'].split();assert raw[0]=='74' and int(raw[1],16)==e['fd']
            assert e['enter_ns']<c['restore_started_ns']<e['exit_ns']
    else:assert c['mode']=='healthy' and c['outcome']=='healthy_completion' and not c['blocked_sync'] and c['exit_before_restore']==c['exit']
    committed=c['committed'];assert committed['state']=='Committed' and committed['details']['files'][0]['attempt']==1 and not committed['details']['source_cleanup_enabled']
    assert [x.split()[0] for x in c['hashes']]==[expected,expected]
    assert [(f['path'],f['size_bytes'],f['algorithm'],f['sha256']) for f in c['manifest']['files']]==[('nested/data.bin',2097169,'sha256',expected)]
    assert c['manifest']['job_id']=='1' and c['manifest']['generator_id']=='fixture' and c['manifest']['submission_id']==c['config']['source_binding']['root_id']
    wire=c['wire'];assert not wire['errors'] and not wire['trace_overflow'] and c['before_wire']['trace'] and wire['trace'][:len(c['before_wire']['trace'])]==c['before_wire']['trace']
    pending={};pairs=[];total=unknown=0
    for row in wire['trace']:
        raw=zlib.decompress(base64.b64decode(row['payload_zlib_base64']));total+=len(raw)
        assert sha(raw)==row['sha256'] and int.from_bytes(raw[:4],'big')==row['xid']
        try:decoded=(call if row['direction']=='call' else reply)(raw)
        except ValueError:decoded=None
        assert decoded==row['decoded'];unknown+=decoded is None
        key=row['connection'],row['xid']
        if row['direction']=='call':pending[key]=row
        elif key in pending:
            request=pending.pop(key);assert request['monotonic_ns']<=row['monotonic_ns'];pairs.append((request,row))
    assert total==wire['trace_bytes'] and total<=64*1048576 and len(wire['trace'])<=8192
    link_pairs=[]
    for request,response in pairs:
        arg,ret=request['decoded'],response['decoded']
        if arg and ret and ret['status']==0 and any(o['op']==11 and o.get('name')=='data' for o in arg['operations']):
            if links[0]['enter_ns']<=request['monotonic_ns']<=response['monotonic_ns']<=links[0]['exit_ns']:
                assert len([o for o in arg['operations'] if o['op']==22])==2
                link_pairs.append(dict(request_sha256=request['sha256'],reply_sha256=response['sha256'],request_ns=request['monotonic_ns'],reply_ns=response['monotonic_ns']))
    assert link_pairs,'no successful original LINK RPC inside the traced source LINK interval'

    def account(event):
        lo,hi=event['enter_ns'],event['exit_ns']
        rows=[dict(direction=r['direction'],sha256=r['sha256'],decoded=r['decoded']) for r in wire['trace'] if lo<=r['monotonic_ns']<=hi]
        spans=[dict(request_sha256=a['sha256'],reply_sha256=b['sha256']) for a,b in pairs if a['monotonic_ns']<lo<=b['monotonic_ns']]
        return dict(path=event['path'],enter_ns=lo,exit_ns=hi,result=event['result'],records=rows,pairs_spanning_entry=spans)
    syncs=[account(x) for x in trace['syncs']]
    selected_account=account(e)
    return dict(profile=c['profile'],phase=c['phase'],mode=c['mode'],outcome=c['outcome'],selected=selected_account,
                all_syncs=syncs,raw_records=len(wire['trace']),unknown_records=unknown,actual_blocked_sync=c['blocked_sync'] is not None,preceding_link_pairs=link_pairs,
                temporal_sync_candidates=[r for r in selected_account['records'] if r['decoded'] and any(o['op'] in (5,38) for o in r['decoded']['operations'])])


_storage=load_module(Path(__file__).with_name('verify-nfs-distinct-recovery.py'),'storage_audit')
analyze_storage=_storage.analyze_storage


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('live',type=Path);parser.add_argument('--production-gate',required=True,type=Path)
    parser.add_argument('--qualification-gate',required=True,type=Path);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    def read(path):return json.loads(path.read_text(encoding='utf-8'))
    def save(name,data):(root/'docs'/name).write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8',newline='\n')
    live=read(args.live/'report.json')
    assert live['claim_sync_discovery'] and not any(live.get(k) for k in ('publication_sync_discovery','claim_remove_death_recovery','claim_link_death_recovery','manifest_link_death_recovery','payload_link_death_recovery','manifest_link_recovery','payload_link_recovery','publication_recovery','verification_recovery','manifest_recovery'))
    assert len(live['sources'])==18 and 'nfs_claim_sync_discovery.py' in live['sources']
    assert live['status']=='PASSED' and live['rust_executed'] and not live['cleanup_errors']
    assert not live['production_nfs_enabled'] and not live['source_deletion_enabled'] and live['glibc']=='glibc 2.22'
    assert live['config']==read(root/'scripts/rust-platform.json')
    for name,item in live['sources'].items():
        data=base64.b64decode(item['base64']);assert sha(data)==item['sha256'] and data==(root/'scripts'/name).read_bytes()
    native=load_module(root/'scripts/verify-nfs-server-recovery.py','native_audit')
    assert len(live['cases'])==4 and {(c['kind'],c['role']) for c in live['cases']}=={(k,r) for k in ('nfsd','container') for r in ('source','destination')}
    native_analysis=[native.analyze_case(c) for c in live['cases']]
    assert all(c['session_changed'] and c['write_verifier_changed'] for c in native_analysis)
    assert live['server_cgroup_setting']=='default' and live['server_host_config']['Cgroups']!='disabled'
    assert live['server_termination_profile']=='nfsd-quiesce-then-sigkill-wait-start'
    for c in live['cases']:
        if c['kind']=='container':
            assert c['quiesced_server']['threads']=='0' and c['quiesced_server']['pid']==c['before_server']['pid']
            assert c['quiesced_server']['container']==c['before_server']['container']
    mounts=[covering(parse(live['inventory']),'/tmp/recovery-'+role) for role in ('source','destination')]
    assert mounts[0]['id']!=mounts[1]['id']
    assert all(m['filesystem']=='nfs4' and m['super']['vers']=='4.1' and m['super']['sec']=='sys' and 'hard' in m['super'] and 'sync' not in m['super'] and 'noac' not in m['super'] for m in mounts)
    cases=live['mover_cases'];assert len(cases)==8 and {(c['profile'],c['phase'],c['mode']) for c in cases}=={(p,h,m) for p in ('debug','release') for h in ('file','directory') for m in ('healthy','nfsd-stopped')}
    for c in cases:
        assert c['binary_sha256']==live['gates']['qualification']['artifacts'][c['profile']]['sha256']
        for role in ('source','destination'):
            observed=covering(parse(live['inventory']),c['config'][role+'_root'])
            declared=c['config'][role+'_binding']['nfs_mount']
            assert declared['profile']=='NMP-41B' and declared['mountpoint']==observed['point']
            assert declared['source']==observed['source'] and declared['addr']==observed['super']['addr']
    storage_analysis=analyze_storage(live)
    for c in cases:
        observed=[covering(parse(live['inventory']),c['config'][role+'_root']) for role in ('source','destination')]
        assert int(c['entry']['descriptor']['mount_id'])==observed[0]['id']
    summaries=[analyze(c,live['inventory']) for c in cases];controls=[]
    for c in cases:
        changes={
            'build_mode':lambda x:x.update(production=True),
            'point':lambda x:x.update(point='wrong'),
            'manifest_job':lambda x:x['manifest'].update(job_id='2'),
            'syscall':lambda x:x['entry'].update(syscall=0),
            'fd':lambda x:x['entry'].update(fd=x['entry']['fd']+1),
            'worker':lambda x:x['trace'].update(pid=0),
            'guard':lambda x:x.update(guard_exit=0),
            'attempt':lambda x:x['committed']['details']['files'][0].update(attempt=2),
            'state':lambda x:x.update(local_after='wrong'),
            'phase':lambda x:x['status_during'].update(state='Claimed'),
            'source':lambda x:x['custody_before']['original'].update(sha256='wrong'),
            'alias':lambda x:x['custody_exit']['private'].update(sha256='wrong'),
            'final':lambda x:x['private_after'].update(identity='wrong'),
            'name_retained':lambda x:x.update(original_absent_at_202=False),
            'wire_hash':lambda x:x['wire']['trace'][-1].update(sha256='wrong'),
            'checkpoint':lambda x:x.update(before_wire=dict(trace=[])),
            'clock':lambda x:x['clock_namespaces'].update(wrong='wrong'),
            'device':lambda x:x.update(filesystem_types=['ef53']*3),
            'artificial_interval':lambda x:x.update(entry_release_ns=x['exit']['exit_ns']+1),
            'exit':lambda x:x['exit'].update(result=-5),
            'manifest':lambda x:x['manifest']['files'][0].update(sha256='wrong'),
            'gate_path':lambda x:x['trace']['gate'].update(path='wrong'),
            'early_reuse':lambda x:x.update(source_reuse_ns=x['handoff_ns']-1),
            'false_202':lambda x:x.update(original_request_before_release='HTTP/1.1 202 Accepted\n\n{"source_paths_released":true}'),
            'request_label':lambda x:x['original_request'].update(parsed=[999,{}]),
            'producer_bytes':lambda x:x.update(producer_after='wrong'),
            'unlink_clock':lambda x:next(e for e in x['trace']['events'] if e['syscall']==263).update(enter_ns=x['exit_release_ns']-1),
            'link_rpc_clock':lambda x:next(e for e in x['trace']['events'] if e['syscall']==265).update(enter_ns=next(e for e in x['trace']['events'] if e['syscall']==265)['exit_ns']),
            'link_name':lambda x:next(e for e in x['trace']['events'] if e['syscall']==265).update(second_pathname='wrong'),
            'sync_order':lambda x:x['trace']['syncs'][0].update(path='wrong'),
            'trace_exit':lambda x:x['trace'].update(exit_status=9),
            'exit_hold':lambda x:x.update(exit_release_ns=x['exit']['observed_ns']-1),
            'outcome':lambda x:x.update(outcome='wrong'),
        }
        if c['mode']=='nfsd-stopped':
            changes['running_backend']=lambda x:x['stopped_server'].update(threads='2')
            changes['restore_clock']=lambda x:x.update(restore_started_ns=0)
        for label,change in changes.items():
            changed=copy.deepcopy(c);change(changed)
            try:analyze(changed,live['inventory'])
            except (AssertionError,ValueError,KeyError):controls.append(dict(profile=c['profile'],phase=c['phase'],mode=c['mode'],control=label,passed=True))
            else:raise AssertionError('bad proof accepted: '+label)
    storage_controls=[]
    for label in ('same_backing','same_client','changed_keeper','writable_reader','changed_server'):
        changed=copy.deepcopy(live)
        if label=='same_backing':
            before=changed['storage']['before'];before['devices']['destination']=before['devices']['source'];changed['storage']['after']=copy.deepcopy(before)
        elif label=='same_client':
            old=changed['storage']['client_devices'][1];new=changed['storage']['client_devices'][0]
            changed['storage']['client_devices'][1]=new
            changed['inventory']='\n'.join(' '.join(line.split()[:2]+[new]+line.split()[3:]) if line.split()[2]==old else line for line in changed['inventory'].splitlines())
        elif label=='changed_keeper':changed['storage']['after']['pid']+=1
        elif label=='writable_reader':
            lines=[]
            for line in changed['storage']['reader_inventory'].splitlines():
                fields=line.split()
                if fields[4] in ('/e/profile-source','/e/profile-destination'):fields[5]=fields[5].replace('ro','rw')
                lines.append(' '.join(fields))
            changed['storage']['reader_inventory']='\n'.join(lines)
        else:changed['cases'][0]['after_server']['storage']['pid']+=1
        try:analyze_storage(changed)
        except (AssertionError,ValueError,KeyError):storage_controls.append(dict(control=label,passed=True))
        else:raise AssertionError('bad storage proof accepted: '+label)
    current={p.relative_to(root/'rust').as_posix():p.read_bytes() for child in (root/'rust').iterdir() if child.name not in ('validation','target') for p in (child.rglob('*') if child.is_dir() else [child]) if p.is_file()}
    auditor=load_module(root/'scripts/check-rust-sles.py','elf_audit')
    binary=(args.live/'probe').read_bytes();assert sha(binary)==live['probe']['sha256'] and auditor.audit(live['probe']['elf_text'])==live['probe']['elf']
    inputs=dict(run_id=live['run_id'],native_analysis=native_analysis,case_analysis=summaries,proof_controls=controls,
                storage_analysis=storage_analysis,storage_controls=storage_controls,rust_input_count=len(current),rust_inputs={n:sha(d) for n,d in current.items()},gates={},
                probe_binary_base64=base64.b64encode(binary).decode())
    gates={};count=0
    for mode,folder,expected in (('production',args.production_gate,211),('qualification',args.qualification_gate,212)):
        gate=read(folder/'report.json');assert gate['status']=='PASSED' and not gate.get('cleanup_error')
        assert gate['config']==live['config'] and gate['build_mode']==('production' if mode=='production' else 'nfs-qualification')
        assert len(gate['dependencies'])==42 and len(gate['audit_negative_controls'])==6
        archive=(folder/'source.tar.gz').read_bytes();assert sha(archive)==gate['source_sha256']
        with tarfile.open(folder/'source.tar.gz') as tar:assert {m.name:tar.extractfile(m).read() for m in tar if m.isfile()}==current
        used=root/'rust/validation'/live['gates'][mode]['run_id']
        used_report=read(used/'report.json')
        assert used_report['status']=='PASSED' and not used_report.get('cleanup_error') and used_report['config']==live['config']
        used_archive=(used/'source.tar.gz').read_bytes();assert sha(used_archive)==live['gates'][mode]['source_sha256']
        with tarfile.open(used/'source.tar.gz') as tar:assert {m.name:tar.extractfile(m).read() for m in tar if m.isfile()}==current
        for profile in ('debug','release'):
            row=gate['profiles'][profile];assert row['tests_passed']==expected and len(row['artifacts'])==10
            for item in row['artifacts']:
                assert sha((folder/item['name']).read_bytes())==item['sha256']
                assert auditor.audit((folder/(item['name']+'.elf')).read_text(encoding='utf-8'))==item['elf'];count+=1
                if not item['test']:
                    assert item['sha256']==live['gates'][mode]['artifacts'][profile]['sha256']
                    prior=next(a for a in used_report['profiles'][profile]['artifacts'] if not a['test'])
                    assert prior==live['gates'][mode]['artifacts'][profile] and sha((used/prior['name']).read_bytes())==item['sha256']
        gates[mode]=gate;inputs['gates'][mode]=dict(run_id=gate['run_id'],source_archive_base64=base64.b64encode(archive).decode(),source_sha256=gate['source_sha256'],
            live_artifact_gate=live['gates'][mode]['run_id'],live_source_archive_base64=base64.b64encode(used_archive).decode(),live_source_sha256=sha(used_archive))
    inventory=read(args.live/'post-run-inventory.json');baseline=read(root/'docs/RUST-NFS-SERVER-RECOVERY-INPUT-EVIDENCE.json')['post_run_inventory']
    for engine in ('default','rootful'):
        assert not inventory[engine]['containers'] and sorted(inventory[engine]['networks'])==sorted(baseline[engine]['networks'])
        assert sorted(inventory[engine]['volume_metadata'],key=lambda v:v['Name'])==sorted(baseline[engine]['volume_metadata'],key=lambda v:v['Name'])
    inputs.update(post_run_inventory=inventory,verified_elf_count=count,source_snapshot_count=len(live['sources']))
    failed_path=root/'docs/RUST-NFS-DISTINCT-RECOVERY-INITIAL-EVIDENCE.json'
    failed=read(failed_path);assert failed['status']=='FAILED_RETAINED'
    for item in failed['files'].values():assert sha(zlib.decompress(base64.b64decode(item['zlib_base64'])))==item['sha256']
    rejected=json.loads(zlib.decompress(base64.b64decode(failed['files']['report.json']['zlib_base64'])))
    assert rejected['status']=='FAILED' and not rejected['cases'] and not rejected['rust_executed']
    assert not rejected['resources']['mounts'] and 'Invalid argument' in rejected['error']
    for item in rejected['sources'].values():assert sha(base64.b64decode(item['base64']))==item['sha256']
    actions=json.loads(zlib.decompress(base64.b64decode(failed['files']['cleanup.json']['zlib_base64'])))
    assert all(a['exit']==0 for a in actions) and not actions[-1]['stdout'].strip()
    inputs['retained_fixture_failures']=[dict(run_id=failed['run_id'],file=failed_path.name,sha256=sha(failed_path.read_bytes()),reason=failed['reason'])]
    initial_path=root/'docs/RUST-NFS-PUBLICATION-SYNC-DISCOVERY-INITIAL-EVIDENCE.json'
    initial=read(initial_path);assert initial['status']=='FAILED_AUDIT_RETAINED'
    retained={}
    for name,item in initial['files'].items():
        payload=zlib.decompress(base64.b64decode(item['zlib_base64']));assert sha(payload)==item['sha256'];retained[name]=payload
    prior=json.loads(retained['report.json']);assert prior['status']=='PASSED' and prior['run_id']==initial['run_id'] and len(prior['mover_cases'])==8
    diagnostic=json.loads(retained['initial-audit-failure.json'])
    assert sha(base64.b64decode(diagnostic['verifier_base64']))==diagnostic['verifier_sha256']
    assert diagnostic['report_sha256']==sha(retained['report.json']) and "KeyError: 'filesystem_devices'" in diagnostic['error']
    inputs['retained_audit_failures']=[dict(file=initial_path.name,sha256=sha(initial_path.read_bytes()),reason=initial['reason'])]

    own_path=root/'docs/RUST-NFS-CLAIM-SYNC-DISCOVERY-INITIAL-EVIDENCE.json'
    own=read(own_path);assert own['status']=='FAILED_RETAINED'
    payloads={}
    for name,item in own['files'].items():
        data=zlib.decompress(base64.b64decode(item['zlib_base64']));assert sha(data)==item['sha256'];payloads[name]=data
    rejected=json.loads(payloads['report.json'])
    assert rejected['run_id']==own['run_id'] and rejected['status']=='FAILED' and rejected['error']=='' and not rejected['cleanup_errors']
    assert len(rejected['cases'])==4 and len(rejected['mover_cases'])==8 and all(c['passed'] for c in rejected['cases']+rejected['mover_cases'])
    old_count=b"(8 if report.get('publication_sync_discovery') else 4)"
    new_count=b"(8 if report.get('publication_sync_discovery') or report.get('claim_sync_discovery') else 4)"
    assert old_count.decode() in rejected['traceback'] and 'AssertionError' in rejected['traceback']
    assert set(rejected['sources'])==set(live['sources'])
    for name,item in rejected['sources'].items():
        data=base64.b64decode(item['base64']);assert sha(data)==item['sha256'] and data==payloads['scripts/'+name]
        if name=='nfs_server_mover.py':assert data.count(old_count)==1;data=data.replace(old_count,new_count)
        assert data==base64.b64decode(live['sources'][name]['base64'])
    prior_inventory=json.loads(payloads['post-run-inventory.json'])
    for engine in ('default','rootful'):
        assert not prior_inventory[engine]['containers'] and sorted(prior_inventory[engine]['networks'])==sorted(inventory[engine]['networks'])
        assert sorted(prior_inventory[engine]['volume_metadata'],key=lambda v:v['Name'])==sorted(inventory[engine]['volume_metadata'],key=lambda v:v['Name'])
    inputs['retained_fixture_failures'].append(dict(file=own_path.name,run_id=own['run_id'],sha256=sha(own_path.read_bytes()),reason=own['reason']))

    regression=subprocess.run([sys.executable,str(root/'scripts/test_nfs_rpc.py'),'-v'],capture_output=True,text=True,timeout=20)
    assert regression.returncode==0;inputs['decoder_regression']=dict(passed=True,output=regression.stdout+regression.stderr)
    inputs['cli_controls']=[]
    for flags in (['--claim-sync-discovery'],['--mover','--distinct-filesystems','--claim-sync-discovery','--claim-remove-death-recovery']):
        before={p.name for p in (root/'rust/validation').iterdir()}
        result=subprocess.run([sys.executable,str(root/'scripts/check-nfs-server-recovery.py'),*flags],capture_output=True,text=True,timeout=20)
        assert result.returncode==2 and '--claim-sync-discovery requires' in result.stderr
        assert {p.name for p in (root/'rust/validation').iterdir()}==before
        inputs['cli_controls'].append(dict(flags=flags,exit_code=result.returncode,stderr=result.stderr,no_provisioning=True))
    for key,path in (('verifier',Path(__file__)),('storage_verifier',root/'scripts/verify-nfs-distinct-recovery.py'),('transitive_verifier',root/'scripts/verify-nfs-server-mover.py'),('native_verifier',root/'scripts/verify-nfs-server-recovery.py'),('gate_auditor',root/'scripts/check-rust-sles.py'),('inventory_collector',root/'scripts/capture-nfs-lab-inventory.py')):
        data=path.read_bytes();inputs[key]=dict(sha256=sha(data),base64=base64.b64encode(data).decode())
    raw=(args.live/'report.json').read_bytes()
    save('RUST-NFS-CLAIM-SYNC-DISCOVERY-EVIDENCE.json',dict(format='zlib-base64-json',report_sha256=sha(raw),report_zlib_base64=base64.b64encode(zlib.compress(raw,9)).decode()))
    save('RUST-NFS-CLAIM-SYNC-DISCOVERY-INPUT-EVIDENCE.json',inputs)
    save('RUST-SLES-EVIDENCE.json',gates['production']);save('RUST-SLES-QUALIFICATION-EVIDENCE.json',gates['qualification'])
    compact=[dict(profile=c['profile'],phase=c['phase'],mode=c['mode'],outcome=c['outcome'],syncs=len(c['all_syncs']),selected_rpc_records=len(c['selected']['records']),selected_spanning_pairs=len(c['selected']['pairs_spanning_entry'])) for c in summaries]
    print(json.dumps(dict(run_id=live['run_id'],cases=compact,native_controls=len(native_analysis),proof_controls=len(controls),storage_controls=len(storage_controls),verified_elf_count=count,cleanup_errors=[])))


if __name__=='__main__':main()
