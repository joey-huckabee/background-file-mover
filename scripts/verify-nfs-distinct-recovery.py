#!/usr/bin/env python3
"""Audit retained actual mover/server-recovery proofs, exact builds and cleanup."""
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


def sha(data):return hashlib.sha256(data).hexdigest()


def load_module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


_base=load_module(Path(__file__).with_name('verify-nfs-server-mover.py'),'mover_audit')


def analyze(c):
    result=_base.analyze(c)
    devices=[c['original_source'][0].split(':')[0],c['staging_before'].split(':')[0],c['original_local_state'].splitlines()[0].split(':')[0]]
    assert len(set(devices))==3,'source, destination and local state must differ'
    assert c['scenario_id']=='SC-122' and not result['shared_client_device']
    result['devices']=devices
    return result


def analyze_storage(live):
    assert live['distinct_filesystems']
    storage=live['storage'];before=storage['before']
    assert before==storage['after'] and before['pid']>0
    assert not storage['persistent_medium'] and storage['bounded_bytes_per_role']==64*1048576 and storage['bounded_inodes_per_role']==4096
    devices=before['devices'];assert devices['source']!=devices['destination']
    client=[covering(parse(live['inventory']),'/tmp/recovery-'+role)['device'] for role in ('source','destination')]
    assert client==storage['client_devices'] and len(set(client))==2
    for target,inventory,readonly in (('/exports',before['inventory'],False),('/e',storage['reader_inventory'],True)):
        for role in ('source','destination'):
            mount=covering(parse(inventory),target+'/profile-'+role)
            assert mount['device']==devices[role] and mount['filesystem']=='tmpfs' and mount['point']==target+'/profile-'+role
            assert mount['super']['size']=='65536k' and mount['super']['nr_inodes']=='4096'
            if readonly:assert 'ro' in mount['vfs']
    assert len(live['storage_volumes'])==2
    for volume in live['storage_volumes']:
        options=volume['Options']
        assert volume['Driver']=='local' and {k:options[k] for k in ('type','device','o')}==dict(type='tmpfs',device='tmpfs',o='size=64m,nr_inodes=4096,mode=1777')
        assert set(options)<={'type','device','o','SIZE'} and options.get('SIZE','64m')=='64m'
    states=[live['initial_server']]
    for c in live['cases']+live['mover_cases']:
        states += [c['before_server'],c['after_server']]
        if 'quiesced_server' in c:states.append(c['quiesced_server'])
        if 'stopped_server' in c:states.append(c['stopped_server'])
    for state in states:
        assert state['storage']==before
        for role in ('source','destination'):
            mount=covering(parse(state['backing_inventory']),'/exports/profile-'+role)
            assert mount['device']==devices[role] and mount['filesystem']=='tmpfs'
    return dict(backing_devices=devices,client_devices=client,keeper_pid=before['pid'],server_observations=len(states),memory_only=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('live',type=Path);parser.add_argument('--production-gate',required=True,type=Path)
    parser.add_argument('--qualification-gate',required=True,type=Path);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    def read(path):return json.loads(path.read_text(encoding='utf-8'))
    def save(name,data):(root/'docs'/name).write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8',newline='\n')
    live=read(args.live/'report.json')
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
    cases=live['mover_cases'];assert len(cases)==4 and {(c['profile'],c['kind']) for c in cases}=={(p,k) for p in ('debug','release') for k in ('nfsd','container')}
    for c in cases:
        for role in ('source','destination'):
            observed=covering(parse(live['inventory']),c['config'][role+'_root'])
            declared=c['config'][role+'_binding']['nfs_mount']
            assert declared['profile']=='NMP-41B' and declared['mountpoint']==observed['point']
            assert declared['source']==observed['source'] and declared['addr']==observed['super']['addr']
    storage_analysis=analyze_storage(live)
    for c in cases:
        observed=[covering(parse(live['inventory']),c['config'][role+'_root']) for role in ('source','destination')]
        assert all(m['device'].startswith('0:') for m in observed)
        assert c['original_source'][0].split(':')[0]==observed[0]['device'].split(':')[1]
        assert c['staging_before'].split(':')[0]==observed[1]['device'].split(':')[1]
    summaries=[analyze(c) for c in cases];controls=[]
    for c in cases:
        labels=('source_bytes','wrong_read','wrong_guard','wrong_attempt','wrong_manifest','wrong_inode','wire_hash','missing_checkpoint','restore_clock','wrong_worker','port_collision','changed_state','shared_device','shared_local_state')
        if c['kind']=='container':labels+=('unquiesced_server',)
        for label in labels:
            changed=copy.deepcopy(c)
            if label=='source_bytes':changed['source_backing_stopped']['sha256']='wrong'
            elif label=='wrong_read':changed['blocked_read']['syscall']='74 0'
            elif label=='wrong_guard':changed['guard_exit']=0
            elif label=='wrong_attempt':changed['committed']['details']['files'][0]['attempt']=2
            elif label=='wrong_manifest':changed['manifest']['files'][0]['sha256']='wrong'
            elif label=='wrong_inode':changed['final_identity']='wrong'
            elif label=='wire_hash':changed['wire']['trace'][-1]['sha256']='wrong'
            elif label=='missing_checkpoint':changed['before_wire']['trace']=[]
            elif label=='restore_clock':changed['restore_started_ns']=2**63
            elif label=='port_collision':changed['contender']['stderr']='Address already in use'
            elif label=='changed_state':changed['local_state_after']='different database'
            elif label=='unquiesced_server':changed['quiesced_server']['threads']='2'
            elif label=='shared_device':
                changed['staging_before']=changed['original_source'][0].split(':')[0]+':'+':'.join(changed['staging_before'].split(':')[1:])
                changed['final_identity']=':'.join(changed['staging_before'].split(':')[:2])
            elif label=='shared_local_state':changed['original_local_state']=changed['original_source'][0].split(':')[0]+':'+':'.join(changed['original_local_state'].split(':')[1:]);changed['local_state_during']=changed['original_local_state'];changed['local_state_after']=changed['original_local_state']
            else:changed['trace']['pid']+=1
            try:analyze(changed)
            except (AssertionError,ValueError):controls.append(dict(profile=c['profile'],kind=c['kind'],control=label,passed=True))
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
    inputs['retained_failed_attempts']=[dict(run_id=failed['run_id'],file=failed_path.name,sha256=sha(failed_path.read_bytes()),reason=failed['reason'])]
    regression=subprocess.run([sys.executable,str(root/'scripts/test_nfs_rpc.py'),'-v'],capture_output=True,text=True,timeout=20)
    assert regression.returncode==0;inputs['decoder_regression']=dict(passed=True,output=regression.stdout+regression.stderr)
    for key,path in (('verifier',Path(__file__)),('mover_verifier',root/'scripts/verify-nfs-server-mover.py'),('native_verifier',root/'scripts/verify-nfs-server-recovery.py'),('gate_auditor',root/'scripts/check-rust-sles.py'),('inventory_collector',root/'scripts/capture-nfs-lab-inventory.py')):
        data=path.read_bytes();inputs[key]=dict(sha256=sha(data),base64=base64.b64encode(data).decode())
    raw=(args.live/'report.json').read_bytes()
    save('RUST-NFS-DISTINCT-RECOVERY-EVIDENCE.json',dict(format='zlib-base64-json',report_sha256=sha(raw),report_zlib_base64=base64.b64encode(zlib.compress(raw,9)).decode()))
    save('RUST-NFS-DISTINCT-RECOVERY-INPUT-EVIDENCE.json',inputs)
    save('RUST-SLES-EVIDENCE.json',gates['production']);save('RUST-SLES-QUALIFICATION-EVIDENCE.json',gates['qualification'])
    print(json.dumps(dict(run_id=live['run_id'],cases=summaries,native_controls=len(native_analysis),proof_controls=len(controls),storage_controls=len(storage_controls),verified_elf_count=count,cleanup_errors=[])))


if __name__=='__main__':main()
