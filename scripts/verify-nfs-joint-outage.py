#!/usr/bin/env python3
"""Audit claimed replay, source revalidation and bounded requests during joint NFS outage."""
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
    assert c['passed'] and c['scenario_id']=='SC-135' and not c['production'] and c['point']=='verify_read'
    assert c['original_state_preserved'] and c['root_identities_stable'] and c['source_retained']
    assert c['handoff']['job_id']==c['replay']['job_id']=='1' and c['handoff']['source_paths_released'] and c['replay']['source_paths_released']
    assert c['status_before']==c['status_during'] and c['status_before']['state']=='Claimed'
    assert c['status_before']['details']['files'][0]['transfer_phase']=='Copied'
    assert c['config']['max_retained_jobs']==1 and c['admission_enabled']==c['config'].get('source_space_admission',{}).get('enabled',False)
    assert c['source_before']==c['source_during'] and c['destination_before']==c['destination_during']
    assert c['source_before']['sha256']==c['destination_before']['sha256']==expected
    assert c['source_before']['identity'].split(':')[2:]==c['destination_before']['identity'].split(':')[2:]==['1','2097169']
    assert c['manifest_absent_during'] and c['guard_exit']==73 and c['health_seconds']<5
    assert c['aged_seconds']>=65 and c['outage_started_ns']<c['after_age_ns']<c['restore_started_ns']
    before=c['before_server'];after=c['after_server']
    assert before['threads']==after['threads']=='2' and c['stopped_server']['threads']==c['still_stopped_server']['threads']=='0'
    for state in (c['stopped_server'],c['still_stopped_server'],after):
        assert all(state[k]==before[k] for k in ('container','pid','started_at','boot_id','netns','address','mounts'))
    delivery=c['delivery_blocked'];validation=c['validation_blocked']
    assert delivery['pid']==c['delivery_pid']==c['paused_worker']['pid'] and delivery['state']==validation['state']=='D'
    assert delivery['number']==int(delivery['syscall'].split()[0])==0 and delivery['path']==c['config']['destination_root']+'/1/.staging/1.part'
    assert int(delivery['syscall'].split()[1],16)==delivery['fd']
    assert validation['number']==int(validation['syscall'].split()[0]) and (validation['path']=='/tmp/recovery-source' or validation['path'].startswith('/tmp/recovery-source/'))
    source=c['config']['source_root'];path=validation['path']
    assert source==path or source.startswith(path+'/') or path.startswith(source+'/')
    assert delivery['pid']!=validation['pid']
    if validation['number'] in (257,262):
        pathname=bytes.fromhex(validation['pathname_hex']).split(b'\0',1)[0].decode()
        assert pathname==validation['pathname'] and validation['directory_fd']==int(validation['syscall'].split()[1],16)
        assert validation['path']==(pathname if pathname.startswith('/') else posixpath.normpath(posixpath.join(validation['directory'],pathname)))
    else:assert validation['number'] in (0,5,138) and int(validation['syscall'].split()[1],16)==validation['fd']
    for worker in (delivery,validation):
        security=dict(x.split(':',1) for x in worker['security'].splitlines() if ':' in x)
        assert security['Uid'].split()==security['Gid'].split()==['1000']*4 and security['NoNewPrivs'].strip()=='1'
        assert all(int(security[k],16)==0 for k in ('CapInh','CapPrm','CapEff'))
    children=c['children_before_burst'];after_children=c['children_after_burst']
    essential=lambda rows:[w for w in rows if '--internal-source-space-worker' not in w['command']]
    assert essential(children)==essential(after_children) and len(essential(children))==2
    for rows in (children,after_children):
        probes=[w for w in rows if '--internal-source-space-worker' in w['command']]
        assert len({w['pid'] for w in rows})==len(rows)==2+len(probes) and len(probes)<=(1 if c['admission_enabled'] else 0)
    gone={w['pid'] for w in children if '--internal-source-space-worker' in w['command']} - {w['pid'] for w in after_children}
    assert set(c['exited_probes'])==gone and all(v in ('gone','Z') for v in c['exited_probes'].values())
    for worker,kind in ((delivery,'delivery'),(validation,'claim')):
        match=next(w for w in children if w['pid']==worker['pid']);assert match['state']=='D' and '--internal-'+kind+'-worker' in match['command']
    if c['admission_enabled']:
        p=c['new_probe_reply'];assert p['seconds']<15 and p['code']==503 and p['body']['error']=='source_space_unavailable' and p['body']['retryable'] and not p['body']['source_paths_released']
        policy=c['config']['source_space_admission'];assert policy==dict(enabled=True,min_available_bytes=1,max_sample_age_seconds=1,probe_timeout_seconds=1)
    assert c['burst_size']==6 and len(c['responses'])==7
    for row in c['responses']:
        head,body=row['raw'].replace('\r\n','\n').split('\n\n',1);assert int(head.split()[1])==row['code']==503 and json.loads(body)==row['body']
        assert row['exit_code']==0 and row['body']['retryable'] and not row['body']['source_paths_released']
        assert row['body']['error'] in ('handoff_pending','service_busy')
        assert row['submission_id'] in (c['config']['source_binding']['root_id'],c['new_body']['submission_id'])
    assert any(row['body']['error']=='service_busy' for row in c['responses'])
    assert c['new_after'][0]==503 and c['new_after'][1]['error']=='retention_capacity' and c['new_after'][1]['retryable'] and not c['new_after'][1]['source_paths_released']
    assert c['retention_during']['details']['retained_jobs']==c['retention_after']['details']['retained_jobs']==1
    assert c['committed']['state']=='Committed' and c['committed']['details']['files'][0]['attempt']==1 and not c['committed']['details']['source_cleanup_enabled']
    assert c['delivery_exit'] in ('gone','Z') and c['validation_exit'] in ('gone','Z')
    assert [x.split()[0] for x in c['hashes']]==[expected,expected]
    assert c['manifest']['job_id']=='1' and c['manifest']['submission_id']==c['config']['source_binding']['root_id']
    assert [(f['path'],f['size_bytes'],f['algorithm'],f['sha256']) for f in c['manifest']['files']]==[('nested/data.bin',2097169,'sha256',expected)]
    mounts=[covering(parse(inventory),c['config'][r+'_root']) for r in ('source','destination')]
    assert mounts[0]['device']!=mounts[1]['device'] and all(m['filesystem']=='nfs4' for m in mounts)
    assert c['filesystem_types'][:2]==['6969','6969'] and c['filesystem_types'][2]!='6969'
    assert c['local_before'].splitlines()[0].split(':')[0] not in [m['device'].split(':')[1] for m in mounts]
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
    spanning=[dict(request_sha256=a['sha256'],reply_sha256=b['sha256']) for a,b in pairs if c['outage_started_ns']<=a['monotonic_ns']<c['restore_started_ns']<b['monotonic_ns']]
    assert any(row['monotonic_ns']<c['outage_started_ns'] for row in wire['trace'])
    assert any(row['monotonic_ns']>c['restore_started_ns'] for row in wire['trace'])
    return dict(profile=c['profile'],admission_enabled=c['admission_enabled'],raw_records=len(wire['trace']),unknown_records=unknown,spanning_restore=spanning,
                response_errors=[r['body']['error'] for r in c['responses']],worker_count=max(len(children),len(after_children)),probe_counts=[sum('--internal-source-space-worker' in w['command'] for w in rows) for rows in (children,after_children)],new_probe_seconds=c.get('new_probe_reply',{}).get('seconds'),outage_seconds=(c['restore_started_ns']-c['outage_started_ns'])/1e9,aged_seconds=c['aged_seconds'],health_seconds=c['health_seconds'],retained_backend_connect_failures=sum(e.get('kind')=='backend_connect_failed' for e in wire.get('transport_events',[])))


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
    assert live['joint_outage'] and not any(live.get(k) for k in ('original_claim_sync_discovery','claim_sync_discovery','publication_sync_discovery','claim_remove_death_recovery','claim_link_death_recovery','manifest_link_death_recovery','payload_link_death_recovery','manifest_link_recovery','payload_link_recovery','publication_recovery','verification_recovery','manifest_recovery'))
    assert len(live['sources'])==17 and 'nfs_joint_outage.py' in live['sources']
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
    cases=live['mover_cases'];assert len(cases)==4 and {(c['profile'],c['admission_enabled']) for c in cases}=={(p,e) for p in ('debug','release') for e in (False,True)}
    for c in cases:
        assert c['binary_sha256']==live['gates']['qualification']['artifacts'][c['profile']]['sha256']
        for role in ('source','destination'):
            observed=covering(parse(live['inventory']),c['config'][role+'_root']);declared=c['config'][role+'_binding']['nfs_mount']
            assert declared['profile']=='NMP-41B' and declared['mountpoint']==observed['point'] and declared['source']==observed['source'] and declared['addr']==observed['super']['addr']
    storage_analysis=analyze_storage(live);summaries=[analyze(c,live['inventory']) for c in cases];controls=[]
    for c in cases:
        changes={
            'mode':lambda x:x.update(production=True),
            'local_state':lambda x:x.update(filesystem_types=['6969']*3),
            'early_202':lambda x:x['responses'][0].update(code=202),
            'false_release':lambda x:x['responses'][0]['body'].update(source_paths_released=True),
            'unbounded_children':lambda x:x['children_after_burst'].append(dict(pid='0')),
            'wrong_source':lambda x:x['validation_blocked'].update(path='/foreign'),
            'wrong_destination':lambda x:x['delivery_blocked'].update(path='/foreign'),
            'not_blocked':lambda x:x['validation_blocked'].update(state='R'),
            'early_restore':lambda x:x.update(restore_started_ns=0),
            'custody':lambda x:x['source_during'].update(sha256='wrong'),
            'stage':lambda x:x['destination_during'].update(identity='wrong'),
            'new_job':lambda x:x['retention_after']['details'].update(retained_jobs=2),
            'manifest':lambda x:x['manifest']['files'][0].update(sha256='wrong'),
            'wire':lambda x:x['wire']['trace'][-1].update(sha256='wrong'),
            'epoch':lambda x:x['after_server'].update(pid=0),
            'age':lambda x:x.update(aged_seconds=0),
            'guard':lambda x:x.update(guard_exit=0),
            'worker_exit':lambda x:x.update(validation_exit='D'),
            'attempt':lambda x:x['committed']['details']['files'][0].update(attempt=2),
        }
        if c['admission_enabled']:changes['probe_response_bound']=lambda x:x['new_probe_reply'].update(seconds=99)
        for label,change in changes.items():
            changed=copy.deepcopy(c);change(changed)
            try:analyze(changed,live['inventory'])
            except (AssertionError,ValueError,KeyError):controls.append(dict(profile=c['profile'],admission_enabled=c['admission_enabled'],control=label,passed=True))
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
    failed_path=root/'docs/RUST-NFS-JOINT-OUTAGE-INITIAL-EVIDENCE.json'
    failed=read(failed_path);assert failed['status']=='FAILED_RETAINED'
    payloads={}
    for name,item in failed['files'].items():
        data=zlib.decompress(base64.b64decode(item['zlib_base64']));assert sha(data)==item['sha256'];payloads[name]=data
    rejected=json.loads(payloads['report.json'])
    assert rejected['status']=='FAILED' and rejected['run_id']==failed['run_id'] and not rejected['cleanup_errors']
    assert len(rejected['cases'])==4 and all(c['passed'] for c in rejected['cases']) and len(rejected['mover_cases'])==1 and not rejected['mover_cases'][0]['passed']
    assert 'fromhex' in rejected['error'] and not json.loads(payloads['rootful-post-containers.json'])
    assert set(rejected['sources'])==set(live['sources'])
    for name,item in rejected['sources'].items():
        data=base64.b64decode(item['base64']);assert sha(data)==item['sha256'] and data==payloads['scripts/'+name]
        if name!='nfs_joint_outage.py':assert data==base64.b64decode(live['sources'][name]['base64'])
    assert b'| od -An -tx1' in payloads['scripts/nfs_joint_outage.py'] and b'| od -An -v -tx1' in base64.b64decode(live['sources']['nfs_joint_outage.py']['base64'])
    inputs['retained_fixture_failures']=[dict(file=failed_path.name,run_id=failed['run_id'],sha256=sha(failed_path.read_bytes()),reason=failed['reason'])]
    second_path=root/'docs/RUST-NFS-JOINT-OUTAGE-SECOND-EVIDENCE.json'
    second=read(second_path);assert second['status']=='FAILED_RETAINED';payloads={}
    for name,item in second['files'].items():
        data=zlib.decompress(base64.b64decode(item['zlib_base64']));assert sha(data)==item['sha256'];payloads[name]=data
    rejected=json.loads(payloads['report.json']);assert rejected['run_id']==second['run_id'] and rejected['status']=='FAILED' and not rejected['cleanup_errors']
    assert len(rejected['cases'])==4 and all(c['passed'] for c in rejected['cases']) and len(rejected['mover_cases'])==2 and rejected['mover_cases'][0]['passed']
    c=rejected['mover_cases'][1];assert c['admission_enabled'] and not c['passed'] and len(c['children_before_burst'])==len(c['children_after_burst'])==2
    assert c['children_before_burst']==c['children_after_burst'] and c['new_probe_reply']['body']['error']=='source_space_unavailable'
    assert len(c['responses'])==7 and all(x['code']==503 and x['body']['retryable'] and not x['body']['source_paths_released'] for x in c['responses'])
    assert 'len(cs)==(3 if enabled else 2)' in rejected['traceback']
    assert set(rejected['sources'])==set(live['sources'])
    for name,item in rejected['sources'].items():
        data=base64.b64decode(item['base64']);assert sha(data)==item['sha256'] and data==payloads['scripts/'+name]
        if name!='nfs_joint_outage.py':assert data==base64.b64decode(live['sources'][name]['base64'])
    prior_inventory=json.loads(payloads['post-run-inventory.json'])
    for engine in ('default','rootful'):
        assert not prior_inventory[engine]['containers'] and sorted(prior_inventory[engine]['networks'])==sorted(inventory[engine]['networks'])
        assert sorted(prior_inventory[engine]['volume_metadata'],key=lambda v:v['Name'])==sorted(inventory[engine]['volume_metadata'],key=lambda v:v['Name'])
    inputs['retained_fixture_failures'].append(dict(file=second_path.name,run_id=second['run_id'],sha256=sha(second_path.read_bytes()),reason=second['reason']))
    inputs['predecessor']=dict(file='RUST-NFS-ORIGINAL-CLAIM-SYNC-DISCOVERY-INPUT-EVIDENCE.json',sha256=sha((root/'docs/RUST-NFS-ORIGINAL-CLAIM-SYNC-DISCOVERY-INPUT-EVIDENCE.json').read_bytes()))
    regression=subprocess.run([sys.executable,str(root/'scripts/test_nfs_rpc.py'),'-v'],capture_output=True,text=True,timeout=20)
    assert regression.returncode==0;inputs['decoder_regression']=dict(passed=True,output=regression.stdout+regression.stderr)
    inputs['cli_controls']=[]
    for flags in (['--joint-outage'],['--mover','--distinct-filesystems','--joint-outage','--claim-sync-discovery']):
        before={p.name for p in (root/'rust/validation').iterdir()}
        result=subprocess.run([sys.executable,str(root/'scripts/check-nfs-server-recovery.py'),*flags],capture_output=True,text=True,timeout=20)
        assert result.returncode==2 and '--joint-outage requires' in result.stderr
        assert {p.name for p in (root/'rust/validation').iterdir()}==before
        inputs['cli_controls'].append(dict(flags=flags,exit_code=result.returncode,stderr=result.stderr,no_provisioning=True))
    for key,path in (('verifier',Path(__file__)),('storage_verifier',root/'scripts/verify-nfs-distinct-recovery.py'),('transitive_verifier',root/'scripts/verify-nfs-server-mover.py'),('native_verifier',root/'scripts/verify-nfs-server-recovery.py'),('gate_auditor',root/'scripts/check-rust-sles.py'),('inventory_collector',root/'scripts/capture-nfs-lab-inventory.py')):
        data=path.read_bytes();inputs[key]=dict(sha256=sha(data),base64=base64.b64encode(data).decode())
    raw=(args.live/'report.json').read_bytes()
    save('RUST-NFS-JOINT-OUTAGE-EVIDENCE.json',dict(format='zlib-base64-json',report_sha256=sha(raw),report_zlib_base64=base64.b64encode(zlib.compress(raw,9)).decode()))
    save('RUST-NFS-JOINT-OUTAGE-INPUT-EVIDENCE.json',inputs)
    save('RUST-SLES-EVIDENCE.json',gates['production']);save('RUST-SLES-QUALIFICATION-EVIDENCE.json',gates['qualification'])
    print(json.dumps(dict(run_id=live['run_id'],cases=summaries,native_controls=len(native_analysis),proof_controls=len(controls),storage_controls=len(storage_controls),verified_elf_count=count,cleanup_errors=[])))


if __name__=='__main__':main()
