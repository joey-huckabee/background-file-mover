#!/usr/bin/env python3
"""Audit inode/size source-change refusal with original pending intent and partial custody retained."""
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
    expected=sha(bytes(2097152)+b'0123456789abcdefg');first_hash=sha(b'first recording payload')
    assert c['passed'] and c['scenario_id']=='SC-138' and not c['production'] and c['point']=='claim_apply' and c['qualification_claim_index']==1 and c['root_identities_stable']
    assert c['phase'] in ('inode','size') and [f['name'] for f in c['submission']['files']]==['earlier/first.bin','nested/data.bin']
    assert c['local_before']==c['local_after'] and c['worker_exit'] in ('gone','Z') and c['guard_exit']==73
    assert c['worker_pid']==c['paused_worker']['pid'] and '--internal-claim-worker' in c['paused_worker']['command']
    assert c['mutation_started_ns']<c['mutation_completed_ns']
    before=c['before_server'];after=c['after_server'];assert before['threads']==after['threads']=='2'
    assert all(after[k]==before[k] for k in ('container','pid','started_at','boot_id','netns','address','mounts'))
    old=c['identity_before'].split(':');changed=c['identity_changed'].split(':')
    assert len(old)==len(changed)==8 and old[0]=='1' and old[3]=='1000' and old[4]=='2097169' and old[7]=='1'
    original=c['original_before'];custody=c['changed_custody'];assert original['sha256']==expected and original['identity'].split(':')[2:]==['1','2097169']
    assert custody['first']==c['first_before'] and custody['first']['sha256']==first_hash and custody['first']['identity'].split(':')[2:]==['1','23']
    assert custody['first_original_absent'] and custody['second_private_absent'] and custody['delivery_absent'] and custody['saved']['sha256']==expected
    assert c['after_refusal_custody']==custody
    if c['phase']=='inode':
        assert old[2]!=changed[2] and old[:2]+old[3:]==changed[:2]+changed[3:]
        assert custody['original']['sha256']==expected and custody['original']['identity'].split(':')[1]!=original['identity'].split(':')[1]
        assert custody['saved']==original
    else:
        assert old[:4]+old[5:]==changed[:4]+changed[5:] and int(changed[4])==int(old[4])+1
        assert custody['original']['sha256']==sha(bytes(2097152)+b'0123456789abcdefgX')
        assert custody['original']['identity'].split(':')[:3]==original['identity'].split(':')[:3] and custody['original']['identity'].split(':')[3]=='2097170'
    row=c['initial_response'];head,body=row['raw'].replace('\r\n','\n').split('\n\n',1)
    assert int(head.split()[1])==row['code'] and json.loads(body)==row['body'] and row['exit_code']==0 and not row['body']['source_paths_released']
    assert (row['code']==409 and row['body']['error']=='recording_blocked' and not row['body']['retryable']) or (row['code']==503 and row['body']['error']=='handoff_pending' and row['body']['retryable'])
    assert 'apply: blocked: relocation object changed' in c['initial_diagnostic']
    assert c['stop_initial']['phase']=='Stopped' and len(c['restarts'])==2
    def status(row):
        st=row['status'];assert st['state']=='Accepted' and not st['source_paths_released'] and st['job_id']=='1'
        d=st['details'];assert d['condition']=='AwaitingClaims' and d['review_epoch']==d['missing_review_epoch']==0 and not d['source_cleanup_enabled']
        assert [f['phase'] for f in d['files']]==['Claimed','Pending'] and all(f['attempt'] is None for f in d['files']) and d['manifest_phase'] is None
        rt=row['retention']['details'];assert rt['retained_jobs']==1 and rt['confirmed_claims']==1 and all(v==0 for v in rt['destination_attempts_by_phase'].values())
    status(c['after_refusal'])
    databases=[c['pending_database'],c['stopped_database']]
    for row in c['restarts']:
        assert row['coordinator_pid']!=c['coordinator_pid'] and len(row['responses'])==3
        for code,body in row['responses']:assert code==409 and body['error']=='recording_blocked' and not body['retryable'] and not body['source_paths_released'] and body['job_id']=='1'
        assert row['custody']==custody and row['identity']==c['identity_changed'] and row['stop']['phase']=='Stopped'
        assert row['status']==c['after_refusal']['status'];status(row);databases.append(row['database'])
    assert c['restarts'][0]['coordinator_pid']!=c['restarts'][1]['coordinator_pid']
    claims=c['pending_database']['claims'];assert len(claims)==2 and [r[-1] for r in claims]==[1,0] and claims[1][-2]==c['identity_before']
    assert [(r[0],r[1],r[3],r[4]) for r in claims]==[(1,0,'current/earlier/first.bin','1-0'),(1,1,'current/nested/data.bin','1-1')]
    import tempfile,sqlite3
    from contextlib import closing
    for database in databases:
        assert database['claims']==claims and database['counts']==dict(jobs=1,files=2,claims=2,transfers=0,manifests=0)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'rust/validation') as folder:
            for name,item in database['files'].items():
                assert name in ('jobs.sqlite','jobs.sqlite-wal');data=zlib.decompress(base64.b64decode(item['zlib_base64']));assert sha(data)==item['sha256'];(Path(folder)/name).write_bytes(data)
            with closing(sqlite3.connect((Path(folder)/'jobs.sqlite').as_uri()+'?mode=ro',uri=True)) as db:
                db.execute('PRAGMA query_only=ON')
                assert [list(row) for row in db.execute('SELECT * FROM claims ORDER BY job_id,file_index')]==claims
                assert {t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in database['counts']}==database['counts']
    assert all('apply: blocked: relocation object changed' in log for log in c['service_logs'].values()) and len(c['service_logs'])==3
    mounts=[covering(parse(inventory),c['config'][r+'_root']) for r in ('source','destination')]
    assert mounts[0]['device']!=mounts[1]['device'] and c['filesystem_types'][:2]==['6969','6969'] and c['filesystem_types'][2]!='6969'
    assert covering(parse(inventory),c['config']['state_database'])['filesystem'] not in ('nfs','nfs4')
    wire=c['wire'];assert not wire['errors'] and not wire['trace_overflow'];total=unknown=0;pending={};pairs=[]
    for row in wire['trace']:
        raw=zlib.decompress(base64.b64decode(row['payload_zlib_base64']));total+=len(raw);assert sha(raw)==row['sha256'] and int.from_bytes(raw[:4],'big')==row['xid']
        try:decoded=(call if row['direction']=='call' else reply)(raw)
        except ValueError:decoded=None
        assert decoded==row['decoded'];unknown+=decoded is None;key=row['connection'],row['xid']
        if row['direction']=='call':pending[key]=row
        elif key in pending:
            request=pending.pop(key);assert request['monotonic_ns']<=row['monotonic_ns'];pairs.append((request,row))
    assert total==wire['trace_bytes'] and total<=64*1048576 and len(wire['trace'])<=8192
    effects={}
    for op,name,label in ((11,'data','first_link'),(28,'first.bin','first_remove')):
        selected=[]
        for request,response in pairs:
            if not(request['decoded'] and response['decoded'] and response['decoded']['status']==0):continue
            if not any(o['op']==op and o.get('name')==name for o in request['decoded']['operations']):continue
            assert response['monotonic_ns']<c['mutation_started_ns']
            selected.append(dict(request_sha256=request['sha256'],reply_sha256=response['sha256']))
        assert selected;effects[label]=selected
    assert not any(row['direction']=='call' and row['decoded'] and any(o['op']==28 and o.get('name')=='data.bin' for o in row['decoded']['operations']) for row in wire['trace'])
    return dict(profile=c['profile'],phase=c['phase'],raw_records=len(wire['trace']),unknown_records=unknown,effects=effects,unpaused_refusals=6,immutable_claim_snapshots=4)


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
    assert live['source_change_refusal'] and not any(live.get(k) for k in ('partial_handoff_replay','pre202_replay','joint_outage','original_claim_sync_discovery','claim_sync_discovery','publication_sync_discovery','claim_remove_death_recovery','claim_link_death_recovery','manifest_link_death_recovery','payload_link_death_recovery','manifest_link_recovery','payload_link_recovery','publication_recovery','verification_recovery','manifest_recovery'))
    assert len(live['sources'])==17 and 'nfs_source_change.py' in live['sources']
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
    cases=live['mover_cases'];assert len(cases)==4 and {(c['profile'],c['phase']) for c in cases}=={(p,h) for p in ('debug','release') for h in ('inode','size')}
    for c in cases:
        assert c['binary_sha256']==live['gates']['qualification']['artifacts'][c['profile']]['sha256']
        for role in ('source','destination'):
            observed=covering(parse(live['inventory']),c['config'][role+'_root']);declared=c['config'][role+'_binding']['nfs_mount']
            assert declared['profile']=='NMP-41B' and declared['mountpoint']==observed['point'] and declared['source']==observed['source'] and declared['addr']==observed['super']['addr']
    storage_analysis=analyze_storage(live);summaries=[analyze(c,live['inventory']) for c in cases];controls=[]
    for c in cases:
        changes={
            'mode':lambda x:x.update(production=True),
            'selector':lambda x:x.update(qualification_claim_index=0),
            'first':lambda x:x['first_before'].update(sha256='wrong'),
            'original':lambda x:x['original_before'].update(sha256='wrong'),
            'identity':lambda x:x.update(identity_changed=x['identity_before']),
            'initial_202':lambda x:x['initial_response'].update(code=202),
            'early_release':lambda x:x['initial_response']['body'].update(source_paths_released=True),
            'effect':lambda x:x['changed_custody'].update(second_private_absent=False),
            'delivery':lambda x:x['changed_custody'].update(delivery_absent=False),
            'claim_done':lambda x:x['pending_database']['claims'][1].__setitem__(-1,1),
            'intent_adoption':lambda x:x['stopped_database']['claims'][1].__setitem__(-2,x['identity_changed']),
            'db_hash':lambda x:x['pending_database']['files']['jobs.sqlite'].update(sha256='wrong'),
            'transfer':lambda x:x['stopped_database']['counts'].update(transfers=1),
            'manifest':lambda x:x['stopped_database']['counts'].update(manifests=1),
            'retryable':lambda x:x['restarts'][0]['responses'][0][1].update(retryable=True),
            'restart_202':lambda x:x['restarts'][1]['responses'][0].__setitem__(0,202),
            'restart_identity':lambda x:x['restarts'][0].update(identity=x['identity_before']),
            'auto_review':lambda x:x['after_refusal']['status']['details'].update(review_epoch=1),
            'confirmed':lambda x:x['after_refusal']['retention']['details'].update(confirmed_claims=2),
            'guard':lambda x:x.update(guard_exit=0),
            'exit':lambda x:x.update(worker_exit='D'),
            'diagnostic':lambda x:x.update(initial_diagnostic='qualification pause failed'),
            'local':lambda x:x.update(local_after='wrong'),
            'wire':lambda x:x['wire']['trace'][-1].update(sha256='wrong'),
            'timing':lambda x:x.update(mutation_started_ns=0),
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
    failure_path=root/'docs/RUST-NFS-SOURCE-CHANGE-AUDIT-INITIAL-EVIDENCE.json'
    failure=read(failure_path);assert failure['status']=='FAILED_RETAINED' and failure['run_id']==live['run_id'];retained={}
    for name,item in failure['files'].items():
        data=zlib.decompress(base64.b64decode(item['zlib_base64']));assert sha(data)==item['sha256'];retained[name]=data
    assert retained['report.json']==(args.live/'report.json').read_bytes()
    diagnostic=retained['diagnostic.txt'].decode(errors='replace');assert 'PermissionError' in diagnostic and 'Temp' in diagnostic
    assert b'with tempfile.TemporaryDirectory() as folder:' in retained['scripts/verify-nfs-source-change.py']
    for name,data in retained.items():
        if name.startswith('scripts/') and name!='scripts/verify-nfs-source-change.py':assert data==(root/name).read_bytes()
    inputs['retained_audit_failure']=dict(file=failure_path.name,sha256=sha(failure_path.read_bytes()),reason=failure['reason'],correction='Workspace-owned extraction directory and explicit SQLite close; raw acquisition unchanged')
    inputs['predecessor']=dict(file='RUST-NFS-PARTIAL-HANDOFF-INPUT-EVIDENCE.json',sha256=sha((root/'docs/RUST-NFS-PARTIAL-HANDOFF-INPUT-EVIDENCE.json').read_bytes()))
    regression=subprocess.run([sys.executable,str(root/'scripts/test_nfs_rpc.py'),'-v'],capture_output=True,text=True,timeout=20)
    assert regression.returncode==0;inputs['decoder_regression']=dict(passed=True,output=regression.stdout+regression.stderr)
    inputs['cli_controls']=[]
    for flags in (['--source-change-refusal'],['--mover','--distinct-filesystems','--source-change-refusal','--joint-outage']):
        before={p.name for p in (root/'rust/validation').iterdir()}
        result=subprocess.run([sys.executable,str(root/'scripts/check-nfs-server-recovery.py'),*flags],capture_output=True,text=True,timeout=20)
        assert result.returncode==2 and '--source-change-refusal requires' in result.stderr
        assert {p.name for p in (root/'rust/validation').iterdir()}==before
        inputs['cli_controls'].append(dict(flags=flags,exit_code=result.returncode,stderr=result.stderr,no_provisioning=True))
    for key,path in (('verifier',Path(__file__)),('storage_verifier',root/'scripts/verify-nfs-distinct-recovery.py'),('transitive_verifier',root/'scripts/verify-nfs-server-mover.py'),('native_verifier',root/'scripts/verify-nfs-server-recovery.py'),('gate_auditor',root/'scripts/check-rust-sles.py'),('inventory_collector',root/'scripts/capture-nfs-lab-inventory.py')):
        data=path.read_bytes();inputs[key]=dict(sha256=sha(data),base64=base64.b64encode(data).decode())
    raw=(args.live/'report.json').read_bytes()
    save('RUST-NFS-SOURCE-CHANGE-EVIDENCE.json',dict(format='zlib-base64-json',report_sha256=sha(raw),report_zlib_base64=base64.b64encode(zlib.compress(raw,9)).decode()))
    save('RUST-NFS-SOURCE-CHANGE-INPUT-EVIDENCE.json',inputs)
    save('RUST-SLES-EVIDENCE.json',gates['production']);save('RUST-SLES-QUALIFICATION-EVIDENCE.json',gates['qualification'])
    print(json.dumps(dict(run_id=live['run_id'],cases=summaries,native_controls=len(native_analysis),proof_controls=len(controls),storage_controls=len(storage_controls),verified_elf_count=count,cleanup_errors=[])))


if __name__=='__main__':main()
