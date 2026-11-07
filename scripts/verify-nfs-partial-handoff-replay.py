#!/usr/bin/env python3
"""Audit multi-file partial source-handoff replay, custody and bounded requests before HTTP 202."""
import argparse
import base64
import copy
import hashlib
import importlib.util
import json
import posixpath
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
    expected=sha(bytes(2097152)+b'0123456789abcdefg')
    assert c['passed'] and c['scenario_id']=='SC-137' and not c['production'] and c['original_state_preserved'] and c['root_identities_stable'] and c['source_retained']
    assert c['qualification_claim_index']==1 and c['first_private_preserved'] and c['first_producer_after']=='next first recording'
    assert [f['name'] for f in c['submission']['files']]==['earlier/first.bin','nested/data.bin']
    first=c['custody_before']['first'];assert first==c['first_before'] and first['sha256']==sha(b'first recording payload') and first['identity'].split(':')[2:]==['1','23']
    assert c['custody_before']['first_original_absent']
    phase=c['phase'];assert phase in ('link','remove') and c['point']==('claim_link_rpc' if phase=='link' else 'claim_unlink_rpc')
    assert c['status_before']==c['status_during'] and c['status_before']['state']=='Accepted' and not c['status_before']['source_paths_released']
    assert c['config']['max_retained_jobs']==1 and not c['config'].get('source_space_admission',{}).get('enabled',False)
    assert c['local_before']==c['local_during']==c['local_after']
    assert c['custody_before']==c['custody_during'] and c['custody_before']['delivery_absent']
    old=c['custody_before']['original'];assert old['sha256']==expected and old['identity'].split(':')[2:]==['1' if phase=='link' else '2','2097169']
    if phase=='link':assert c['custody_before']['private'] is None
    else:assert c['custody_before']['private']==old
    parts=old['identity'].split(':');assert c['private_after']==dict(identity=':'.join(parts[:2]+['1',parts[3]]),sha256=expected)
    assert c['original_absent_at_202'] and c['producer_after']=='next recording'
    assert c['outage_started_ns']<c['restore_started_ns']<c['handoff_ns']<c['source_reuse_ns']
    before=c['before_server'];after=c['after_server'];assert before['threads']==after['threads']=='2'
    for row in (c['stopped_server'],c['still_stopped_server']):assert row['threads']=='0'
    for row in (c['stopped_server'],c['still_stopped_server'],after):assert all(row[k]==before[k] for k in ('container','pid','started_at','boot_id','netns','address','mounts'))
    b=c['blocked'];f=b['syscall'].split();assert b['state']=='D' and len(f)==9 and f[0]==('265' if phase=='link' else '263') and int(f[1],16)==b['fd']
    assert b['path']==c['config']['source_root']+'/current/nested'
    if phase=='link':assert int(f[3],16)==b['newfd'] and b['newpath']==c['config']['source_root']+'/.file-mover/1-1' and int(f[5],16)==0
    else:assert int(f[3],16)==0
    assert c['worker_pid']==c['paused_worker']['pid'] and '--internal-claim-worker' in c['paused_worker']['command']
    assert c['children_before']==c['children_during']==[c['worker_pid']] and c['epoch_before']==c['epoch_during'] and c['epoch_before']['group']==int(c['coordinator_pid'])
    assert c['guard_exit']==73 and c['health_seconds']<5 and c['worker_exit'] in ('gone','Z')
    sec=dict(x.split(':',1) for x in c['security'].splitlines() if ':' in x)
    assert sec['Uid'].split()==sec['Gid'].split()==['1000']*4 and sec['NoNewPrivs'].strip()=='1' and all(int(sec[k],16)==0 for k in ('CapInh','CapPrm','CapEff'))
    assert c['burst_size']==6 and len(c['responses'])==7
    for row in c['responses']:
        head,body=row['raw'].replace('\r\n','\n').split('\n\n',1);assert int(head.split()[1])==row['code']==503 and json.loads(body)==row['body']
        assert row['exit_code']==0 and row['body']['error'] in ('handoff_pending','service_busy') and row['body']['retryable'] and not row['body']['source_paths_released']
        assert row['submission_id'] in (c['config']['source_binding']['root_id'],c['new_body']['submission_id'])
    assert any(r['body']['error']=='service_busy' for r in c['responses'])
    assert c['retry_responses'][-1]==[202,c['handoff']] and c['handoff']['job_id']==c['replay']['job_id']=='1' and c['handoff']['source_paths_released'] and c['replay']['source_paths_released']
    for code,body in c['retry_responses'][:-1]:assert code==503 and body['error'] in ('handoff_pending','service_busy') and body['retryable'] and not body['source_paths_released']
    assert c['retention_during']['details']['retained_jobs']==1 and c['retention_during']['details']['confirmed_claims']==1
    assert all(v==0 for v in c['retention_during']['details']['destination_attempts_by_phase'].values())
    assert c['new_after'][0]==503 and c['new_after'][1]['error']=='retention_capacity' and c['new_after'][1]['retryable'] and not c['new_after'][1]['source_paths_released']
    assert c['committed']['state']=='Committed' and len(c['committed']['details']['files'])==2 and all(f['attempt']==1 for f in c['committed']['details']['files']) and not c['committed']['details']['source_cleanup_enabled']
    first_hash=sha(b'first recording payload')
    assert [[x.split()[0] for x in lines] for lines in c['hashes']]==[[first_hash]*2,[expected]*2] and c['manifest']['job_id']=='1'
    assert [(f['path'],f['size_bytes'],f['algorithm'],f['sha256']) for f in c['manifest']['files']]==[('earlier/first.bin',23,'sha256',first_hash),('nested/data.bin',2097169,'sha256',expected)]
    assert c['manifest']['submission_id']==c['config']['source_binding']['root_id'] and c['manifest']['generator_id']=='fixture'
    assert sha(json.dumps(c['manifest'],separators=(',',':'),ensure_ascii=False).encode())==c['manifest_sha256']
    mounts=[covering(parse(inventory),c['config'][r+'_root']) for r in ('source','destination')]
    assert mounts[0]['device']!=mounts[1]['device'] and c['filesystem_types'][:2]==['6969','6969'] and c['filesystem_types'][2]!='6969'
    assert c['local_before'].splitlines()[0].split(':')[0] not in [m['device'].split(':')[1] for m in mounts]
    assert int(dict(line.split(':',1) for line in b['fdinfo'].splitlines())['mnt_id'])==mounts[0]['id']
    wire=c['wire'];assert not wire['errors'] and not wire['trace_overflow'];total=unknown=0;pending={};pairs=[]
    for row in wire['trace']:
        raw=zlib.decompress(base64.b64decode(row['payload_zlib_base64']));total+=len(raw)
        assert sha(raw)==row['sha256'] and int.from_bytes(raw[:4],'big')==row['xid']
        try:decoded=(call if row['direction']=='call' else reply)(raw)
        except ValueError:decoded=None
        assert decoded==row['decoded'];unknown+=decoded is None;key=row['connection'],row['xid']
        if row['direction']=='call':pending[key]=row
        elif key in pending:
            request=pending.pop(key);assert request['monotonic_ns']<=row['monotonic_ns'];pairs.append((request,row))
    assert total==wire['trace_bytes'] and total<=64*1048576 and len(wire['trace'])<=8192
    effects={}
    successful=[(a,b) for a,b in pairs if a['decoded'] and b['decoded'] and b['decoded']['status']==0]
    def has(a,op,name):return any(o['op']==op and o.get('name')==name for o in a['decoded']['operations'])
    first_removes=[(a,b) for a,b in successful if has(a,28,'first.bin')]
    assert first_removes and all(b['monotonic_ns']<c['outage_started_ns'] for a,b in first_removes)
    links=[(a,b) for a,b in successful if has(a,11,'data')]
    early=[(a,b) for a,b in links if b['monotonic_ns']<c['outage_started_ns']]
    assert len(early)>=(1 if phase=='link' else 2)
    assert len({tuple(o['filehandle_sha256'] for o in a['decoded']['operations'] if o['op']==22) for a,b in links})>=2
    signatures={tuple(o['filehandle_sha256'] for o in a['decoded']['operations'] if o['op']==22) for a,b in early}
    assert len(signatures)>=(1 if phase=='link' else 2)
    for op,name,key in ((11,'data','link'),(28,'data.bin','remove')):
        selected=[]
        for a,b in successful:
            if not has(a,op,name):continue
            if key=='link' and phase=='remove':
                if b['monotonic_ns']>=c['outage_started_ns']:continue
            else:
                if a['monotonic_ns']<=c['outage_started_ns']:continue
                assert b['monotonic_ns']>c['restore_started_ns']
            selected.append(dict(request_sha256=a['sha256'],reply_sha256=b['sha256'],request_ns=a['monotonic_ns'],reply_ns=b['monotonic_ns']))
        assert selected,'missing successful source '+key+' pair';effects[key]=selected
    effects['first_remove']=[dict(request_sha256=a['sha256'],reply_sha256=b['sha256'],reply_ns=b['monotonic_ns']) for a,b in first_removes]
    return dict(profile=c['profile'],phase=phase,raw_records=len(wire['trace']),unknown_records=unknown,effects=effects,
                response_errors=[r['body']['error'] for r in c['responses']],health_seconds=c['health_seconds'],outage_seconds=(c['restore_started_ns']-c['outage_started_ns'])/1e9)


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
    assert live['partial_handoff_replay'] and not any(live.get(k) for k in ('pre202_replay','joint_outage','original_claim_sync_discovery','claim_sync_discovery','publication_sync_discovery','claim_remove_death_recovery','claim_link_death_recovery','manifest_link_death_recovery','payload_link_death_recovery','manifest_link_recovery','payload_link_recovery','publication_recovery','verification_recovery','manifest_recovery'))
    assert len(live['sources'])==17 and 'nfs_partial_handoff_replay.py' in live['sources']
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
    cases=live['mover_cases'];assert len(cases)==4 and {(c['profile'],c['phase']) for c in cases}=={(p,h) for p in ('debug','release') for h in ('link','remove')}
    for c in cases:
        assert c['binary_sha256']==live['gates']['qualification']['artifacts'][c['profile']]['sha256']
        for role in ('source','destination'):
            observed=covering(parse(live['inventory']),c['config'][role+'_root']);declared=c['config'][role+'_binding']['nfs_mount']
            assert declared['profile']=='NMP-41B' and declared['mountpoint']==observed['point'] and declared['source']==observed['source'] and declared['addr']==observed['super']['addr']
    storage_analysis=analyze_storage(live);summaries=[analyze(c,live['inventory']) for c in cases];controls=[]
    for c in cases:
        changes={
            'mode':lambda x:x.update(production=True),
            'early_202':lambda x:x['responses'][0].update(code=202),
            'false_release':lambda x:x['responses'][0]['body'].update(source_paths_released=True),
            'replacement_worker':lambda x:x['children_during'].append('0'),
            'path':lambda x:x['blocked'].update(path='/foreign'),
            'state':lambda x:x['blocked'].update(state='R'),
            'fd':lambda x:x['blocked'].update(fd=x['blocked']['fd']+1),
            'early_reuse':lambda x:x.update(source_reuse_ns=x['handoff_ns']-1),
            'custody':lambda x:x['custody_during']['original'].update(sha256='wrong'),
            'premature_delivery':lambda x:x['custody_during'].update(delivery_absent=False),
            'confirmed_claim':lambda x:x['retention_during']['details'].update(confirmed_claims=0),
            'first_custody':lambda x:x['custody_during']['first'].update(sha256='wrong'),
            'first_original':lambda x:x['custody_before'].update(first_original_absent=False),
            'selector':lambda x:x.update(qualification_claim_index=0),
            'first_payload':lambda x:x['first_before'].update(sha256='wrong'),
            'second_attempt':lambda x:x['committed']['details']['files'][1].update(attempt=2),
            'second_manifest':lambda x:x['manifest']['files'][1].update(sha256='wrong'),
            'extra_job':lambda x:x['retention_during']['details'].update(retained_jobs=2),
            'manifest':lambda x:x['manifest']['files'][0].update(sha256='wrong'),
            'manifest_hash':lambda x:x.update(manifest_sha256='wrong'),
            'wire':lambda x:x['wire']['trace'][-1].update(sha256='wrong'),
            'epoch':lambda x:x['epoch_during'].update(group=0),
            'guard':lambda x:x.update(guard_exit=0),
            'worker_exit':lambda x:x.update(worker_exit='D'),
            'attempt':lambda x:x['committed']['details']['files'][0].update(attempt=2),
            'local_state':lambda x:x.update(local_after='wrong'),
            'early_restore':lambda x:x.update(restore_started_ns=0),
        }
        for label,change in changes.items():
            changed=copy.deepcopy(c);change(changed)
            try:analyze(changed,live['inventory'])
            except (AssertionError,ValueError,KeyError):controls.append(dict(profile=c['profile'],phase=c['phase'],control=label,passed=True))
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
    for mode,folder,expected in (('production',args.production_gate,211),('qualification',args.qualification_gate,213)):
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
    initial_path=root/'docs/RUST-NFS-PARTIAL-HANDOFF-INITIAL-EVIDENCE.json'
    initial=read(initial_path);assert initial['status']=='FAILED_RETAINED'
    import io
    unformatted=dict(current)
    key='crates/mover-fs/src/qualification.rs'
    text=current[key].decode().replace('let selected = value\n                .parse::<usize>()\n                .ok()\n                .filter(|n| *n < 256)','let selected = value.parse::<usize>().ok().filter(|n| *n < 256)').replace('std::env::var("FILE_MOVER_QUALIFICATION_CLAIM_INDEX")\n            .ok()\n            .as_deref(),','std::env::var("FILE_MOVER_QUALIFICATION_CLAIM_INDEX").ok().as_deref(),')
    assert text.encode()!=current[key];unformatted[key]=text.encode()
    for name,item in initial['files'].items():
        data=zlib.decompress(base64.b64decode(item['zlib_base64']));assert sha(data)==item['sha256']
        if name.endswith('/source.tar.gz'):
            with tarfile.open(fileobj=io.BytesIO(data)) as tar:assert {m.name:tar.extractfile(m).read() for m in tar if m.isfile()}==unformatted
        if name.endswith('/report.json'):
            failed=json.loads(data);assert failed['status']=='FAILED' and 'Diff in /work/crates/mover-fs/src/qualification.rs' in failed['error'] and not failed.get('cleanup_error')
    inputs['retained_initial_gate_failure']=dict(file=initial_path.name,sha256=sha(initial_path.read_bytes()),reason=initial['reason'])
    second_path=root/'docs/RUST-NFS-PARTIAL-HANDOFF-SECOND-EVIDENCE.json'
    second=read(second_path);assert second['status']=='FAILED_RETAINED';retained={}
    for name,item in second['files'].items():
        data=zlib.decompress(base64.b64decode(item['zlib_base64']));assert sha(data)==item['sha256'];retained[name]=data
    rejected=json.loads(retained['report.json'])
    assert rejected['status']=='FAILED' and rejected['run_id']==second['run_id'] and not rejected['cleanup_errors'] and not rejected['rust_executed'] and not rejected['mover_cases']
    assert len(rejected['cases'])==4 and all(c['passed'] for c in rejected['cases'])
    assert 'No such file or directory' in rejected['error'] and 'nfs-qualification' in rejected['error'] and 'report.json' in rejected['error']
    assert set(rejected['sources'])==set(live['sources'])
    for name,item in rejected['sources'].items():
        data=base64.b64decode(item['base64']);assert sha(data)==item['sha256'] and data==retained['scripts/'+name]==base64.b64decode(live['sources'][name]['base64'])
    for engine in ('default','rootful'):
        inv=second['post_run_inventory'][engine]
        assert not inv['containers'] and sorted(inv['networks'])==sorted(baseline[engine]['networks'])
        assert sorted(inv['volume_metadata'],key=lambda v:v['Name'])==sorted(baseline[engine]['volume_metadata'],key=lambda v:v['Name'])
    inputs['retained_acquisition_failure']=dict(file=second_path.name,run_id=second['run_id'],sha256=sha(second_path.read_bytes()),reason=second['reason'])
    inputs['predecessor']=dict(file='RUST-NFS-PRE202-REPLAY-INPUT-EVIDENCE.json',sha256=sha((root/'docs/RUST-NFS-PRE202-REPLAY-INPUT-EVIDENCE.json').read_bytes()))
    regression=subprocess.run([sys.executable,str(root/'scripts/test_nfs_rpc.py'),'-v'],capture_output=True,text=True,timeout=20)
    assert regression.returncode==0;inputs['decoder_regression']=dict(passed=True,output=regression.stdout+regression.stderr)
    inputs['cli_controls']=[]
    for flags in (['--partial-handoff-replay'],['--mover','--distinct-filesystems','--partial-handoff-replay','--joint-outage']):
        before={p.name for p in (root/'rust/validation').iterdir()}
        result=subprocess.run([sys.executable,str(root/'scripts/check-nfs-server-recovery.py'),*flags],capture_output=True,text=True,timeout=20)
        assert result.returncode==2 and '--partial-handoff-replay requires' in result.stderr
        assert {p.name for p in (root/'rust/validation').iterdir()}==before
        inputs['cli_controls'].append(dict(flags=flags,exit_code=result.returncode,stderr=result.stderr,no_provisioning=True))
    for key,path in (('verifier',Path(__file__)),('storage_verifier',root/'scripts/verify-nfs-distinct-recovery.py'),('transitive_verifier',root/'scripts/verify-nfs-server-mover.py'),('native_verifier',root/'scripts/verify-nfs-server-recovery.py'),('gate_auditor',root/'scripts/check-rust-sles.py'),('inventory_collector',root/'scripts/capture-nfs-lab-inventory.py')):
        data=path.read_bytes();inputs[key]=dict(sha256=sha(data),base64=base64.b64encode(data).decode())
    raw=(args.live/'report.json').read_bytes()
    save('RUST-NFS-PARTIAL-HANDOFF-EVIDENCE.json',dict(format='zlib-base64-json',report_sha256=sha(raw),report_zlib_base64=base64.b64encode(zlib.compress(raw,9)).decode()))
    save('RUST-NFS-PARTIAL-HANDOFF-INPUT-EVIDENCE.json',inputs)
    save('RUST-SLES-EVIDENCE.json',gates['production']);save('RUST-SLES-QUALIFICATION-EVIDENCE.json',gates['qualification'])
    print(json.dumps(dict(run_id=live['run_id'],cases=summaries,native_controls=len(native_analysis),proof_controls=len(controls),storage_controls=len(storage_controls),verified_elf_count=count,cleanup_errors=[])))


if __name__=='__main__':main()
