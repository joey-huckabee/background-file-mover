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
from nfs_rpc import call, reply


def sha(data):return hashlib.sha256(data).hexdigest()


def load_module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def _analyze(c):
    expected=sha(bytes(2*1048576)+b'0123456789abcdefg')
    assert c['passed'] and c['original_state_preserved'] and c['root_identities_stable'] and c['source_retained']
    assert c['handoff']['job_id']==c['replay']['job_id']=='1'
    assert c['handoff']['source_paths_released'] and c['replay']['source_paths_released']
    assert c['source_backing_before']==c['source_backing_stopped']==c['source_backing_after']
    assert c['source_backing_before']['sha256']==expected
    assert c['original_source'][0].split(':')[-1]=='2097169'
    assert c['staging_before'].split(':')[-1]=='2097169'
    assert c['filesystem_types'][:2]==['6969','6969'] and c['filesystem_types'][2]!='6969'
    assert c['original_source'][0].split(':')[:2]!=c['staging_before'].split(':')[:2]
    assert c['final_identity']==':'.join(c['staging_before'].split(':')[:2])
    assert c['status_before']==c['status_during'] and c['status_before']['state']=='Claimed'
    assert c['status_before']['details']['files'][0]['transfer_phase']=='PublishIntent'
    blocked=c['blocked_unlink'];raw=blocked['syscall'].split()
    assert blocked['state']=='D'
    assert raw[0]=='263' and int(raw[1],16)==blocked['fd'] and int(raw[3],16)==0
    assert blocked['path']==c['config']['destination_root']+'/1/.staging'
    assert c['worker_pid']==c['paused_worker']['pid'] and c['epoch_before']['group']==int(c['coordinator_pid'])
    assert '--internal-delivery-worker' in c['paused_worker']['command']
    assert c['guard_exit']==73 and c['contender']['exit_code']!=0
    assert 'local instance or surviving worker already owns state' in c['contender']['stderr']
    assert c['contender']['seconds']<6 and c['contender']['config']==dict(c['config'],bind='127.0.0.1:0')
    assert c['epoch_during']==c['epoch_before'] and c['coordinator_after']==c['coordinator_pid']
    assert c['original_local_state']==c['local_state_during']==c['local_state_after']
    assert c['original_enrollment']==c['enrollment_after']
    security=dict(line.split(':',1) for line in c['worker_security'].splitlines() if ':' in line)
    assert security['Uid'].split()==security['Gid'].split()==['1000']*4 and security['NoNewPrivs'].strip()=='1'
    assert all(int(security[k],16)==0 for k in ('CapInh','CapPrm','CapEff'))
    assert c['health_seconds']<5 and c['worker_exit'] in ('gone','Z')
    assert len(set(c['clock_namespaces'].values()))==1
    before,after=c['before_server'],c['after_server']
    assert before['container']==after['container'] and before['address']==after['address']
    assert before['image']==after['image'] and before['mounts']==after['mounts']
    assert before['boot_id']==after['boot_id'] and before['threads']==after['threads']=='2'
    if c['kind']=='nfsd':
        assert c['stopped_server']['threads']=='0' and before['pid']==after['pid']
        assert before['started_at']==after['started_at'] and before['netns']==after['netns']
    else:
        assert c['quiesced_server']['threads']=='0' and c['quiesced_server']['container']==before['container']
        assert c['quiesced_server']['pid']==before['pid'] and c['quiesced_server']['started_at']==before['started_at']
        assert c['stop_exit_code']==137 and c['stopped_container']['Status']=='exited'
        assert c['stopped_container']['Pid']==0 and not c['stopped_container']['Running']
        assert before['pid']!=after['pid'] and before['started_at']!=after['started_at']
    trace=c['trace'];assert trace['passed'] and not trace.get('cleanup_error') and trace['pid']==int(c['worker_pid'])
    assert trace['exit_status'] in (0,9) and all(s['result']==0 for s in trace['syncs'])
    stage=c['config']['destination_root']+'/1/.staging/1.part'
    assert trace['syncs'] and all(s['enter_ns']>=c['restore_started_ns'] for s in trace['syncs'])
    unlink=verify_publication_proof(c)
    committed=c['committed'];assert committed['state']=='Committed' and not committed['details']['source_cleanup_enabled']
    assert committed['details']['files'][0]['attempt']==1
    assert [line.split()[0] for line in c['hashes']]==[expected,expected]
    manifest=c['manifest'];assert manifest['job_id']=='1' and manifest['generator_id']=='fixture'
    assert manifest['submission_id']==c['config']['source_binding']['root_id']
    assert [(f['path'],f['size_bytes'],f['algorithm'],f['sha256']) for f in manifest['files']]==[('nested/data.bin',2097169,'sha256',expected)]
    wire=c['wire'];assert not wire['errors'] and not wire['trace_overflow']
    assert c['before_wire']['trace'] and wire['trace'][:len(c['before_wire']['trace'])]==c['before_wire']['trace']
    pending={};pairs=[];total=unknown=0
    for index,row in enumerate(wire['trace']):
        data=zlib.decompress(base64.b64decode(row['payload_zlib_base64']));total+=len(data)
        assert sha(data)==row['sha256'] and int.from_bytes(data[:4],'big')==row['xid']
        try:decoded=(call if row['direction']=='call' else reply)(data)
        except ValueError:decoded=None
        assert decoded==row['decoded'];unknown+=decoded is None
        key=row['connection'],row['xid']
        if row['direction']=='call':pending[key]=(row,index)
        elif key in pending:
            request,entry=pending.pop(key);assert request['monotonic_ns']<=row['monotonic_ns']
            pairs.append((request,row,entry))
    assert total==wire['trace_bytes'] and total<=64*1048576 and len(wire['trace'])<=8192
    errors=[];writes=[];removes=[]
    for request,response,index in pairs:
        arg,ret=request['decoded'],response['decoded']
        if not arg or not ret:continue
        if ret['status']:errors.append(ret['status']);continue
        for op,result in zip(arg['operations'],ret['operations']):
            assert op['op']==result['op'] and result['status']==0
            if op['op']==28 and op['name']=='1.part' and unlink['enter_ns']<=request['monotonic_ns']<=response['monotonic_ns']<=unlink['exit_ns'] and response['monotonic_ns']>=c['restore_started_ns']:
                removes.append(dict(name=op['name'],filehandle_sha256=next(o['filehandle_sha256'] for o in arg['operations'] if o['op']==22),request_sha256=request['sha256'],reply_sha256=response['sha256']))
            if op['op']==38 and response['monotonic_ns']>=c['restore_started_ns']:
                assert op['count']==result['count']
                writes.append(dict(filehandle_sha256=next(o['filehandle_sha256'] for o in arg['operations'] if o['op']==22),
                                   offset=op['offset'],count=op['count'],stable=op['stable'],committed=result['committed'],
                                   verifier=result['verifier_hex'],request_sha256=request['sha256'],reply_sha256=response['sha256']))
    assert writes,'no successful post-restoration manifest WRITE evidence'
    assert removes,'no successful REMOVE inside the pending staging-unlink interval'
    return dict(profile=c['profile'],kind=c['kind'],publication_unlink_blocked=True,same_worker_attempt=1,
                shared_client_device=c['original_source'][0].split(':')[0]==c['staging_before'].split(':')[0],
                retained_staging_inode=True,protocol_errors=errors,post_restore_writes=writes,post_restore_removes=removes,
                netns_changed=before['netns']!=after['netns'],raw_records=len(wire['trace']),unknown_records=unknown)


_storage=load_module(Path(__file__).with_name('verify-nfs-distinct-recovery.py'),'storage_audit')
analyze_storage=_storage.analyze_storage


def verify_publication_proof(c):
    trace=c['trace'];parent=c['config']['destination_root']+'/1/.staging'
    assert trace['syncs']==[e for e in trace['events'] if e['syscall'] in (74,75)]
    blocked=c['blocked_unlink'];fdinfo=dict(line.split(':',1) for line in blocked['fdinfo'].splitlines())
    events=[e for e in trace['events'] if e['syscall']==263 and e.get('descriptor') and e['descriptor']['path']==parent and e.get('pathname')=='1.part']
    assert len(events)==1
    e=events[0];d=e['descriptor']
    assert e['args'][0]==blocked['fd'] and e['args'][2]==0 and e['result']==0
    assert e['args'][:3]==[int(value,16) for value in blocked['syscall'].split()[1:4]]
    assert d['filesystem']=='nfs4' and d['mount_id']==fdinfo['mnt_id'].strip() and d['inode']==int(fdinfo['ino'])
    assert e['enter_ns']<c['restore_started_ns']<e['exit_ns']
    aliases=c['aliases_before'];assert aliases==c['aliases_stopped'] and aliases['manifest_absent']
    assert aliases['staging']==aliases['final']
    identity=aliases['staging']['identity'].split(':')
    assert identity[-2:]==['2','2097169'] and aliases['staging']['sha256']==c['source_backing_before']['sha256']
    assert c['final_backing_after']==dict(identity=':'.join(identity[:2]+['1',identity[3]]),sha256=aliases['final']['sha256'])
    assert c['staging_absent_after']
    pubs=[x for x in trace['events'] if x['syscall'] in (264,265,316) and x.get('result')==0 and x.get('second_pathname')=='COMMITTED.json']
    assert pubs and all(x['enter_ns']>=e['exit_ns'] and x['second_directory']['path']==c['config']['destination_root']+'/1' for x in pubs)
    assert not any(x['syscall'] in (264,265,316) and x.get('result')==0 and x.get('second_pathname')=='data.bin' for x in trace['events'])
    return e


def analyze(c):
    result=_analyze(c)
    devices=[c['original_source'][0].split(':')[0],c['staging_before'].split(':')[0],c['original_local_state'].splitlines()[0].split(':')[0]]
    assert len(set(devices))==3
    assert c['point']=='file_unlink' and c['scenario_id']=='SC-124' and not result['shared_client_device']
    result.update(devices=devices,original_two_name_aliases=True,staging_removed_after_restore=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('live',type=Path);parser.add_argument('--production-gate',required=True,type=Path)
    parser.add_argument('--qualification-gate',required=True,type=Path);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    def read(path):return json.loads(path.read_text(encoding='utf-8'))
    def save(name,data):(root/'docs'/name).write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8',newline='\n')
    live=read(args.live/'report.json')
    assert live['publication_recovery'] and not live['verification_recovery']
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
    for c in cases:
        fdinfo=dict(line.split(':',1) for line in c['blocked_unlink']['fdinfo'].splitlines())
        assert int(fdinfo['mnt_id'])==covering(parse(live['inventory']),c['config']['destination_root'])['id']
    summaries=[analyze(c) for c in cases];controls=[]
    for c in cases:
        labels=('source_bytes','wrong_unlink','wrong_guard','wrong_attempt','wrong_manifest','wrong_inode','wire_hash','missing_checkpoint','restore_clock','wrong_worker','port_collision','changed_state','shared_device','shared_local_state','wrong_phase','wrong_parent','changed_alias','one_alias','early_manifest','failed_unlink','unlink_clock','wrong_name','retained_stage','changed_sync_event','remove_window','wrong_manifest_order','wrong_final_links')
        if c['kind']=='container':labels+=('unquiesced_server',)
        for label in labels:
            changed=copy.deepcopy(c)
            if label=='source_bytes':changed['source_backing_stopped']['sha256']='wrong'
            elif label=='wrong_unlink':changed['blocked_unlink']['syscall']='0 0'
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
            elif label=='shared_local_state':
                changed['original_local_state']=changed['original_source'][0].split(':')[0]+':'+':'.join(changed['original_local_state'].split(':')[1:])
                changed['local_state_during']=changed['original_local_state'];changed['local_state_after']=changed['original_local_state']
            elif label=='wrong_phase':changed['status_before']['details']['files'][0]['transfer_phase']='Copied';changed['status_during']=copy.deepcopy(changed['status_before'])
            elif label=='wrong_parent':changed['blocked_unlink']['path']=changed['config']['source_root']+'/.file-mover'
            elif label=='changed_alias':changed['aliases_stopped']['final']['sha256']='wrong'
            elif label=='one_alias':
                for state in ('aliases_before','aliases_stopped'):
                    for role in ('staging','final'):
                        parts=changed[state][role]['identity'].split(':');parts[2]='1';changed[state][role]['identity']=':'.join(parts)
            elif label=='early_manifest':changed['aliases_stopped']['manifest_absent']=False
            elif label=='retained_stage':changed['staging_absent_after']=False
            elif label=='wrong_manifest_order':next(e for e in changed['trace']['events'] if e['syscall'] in (264,265,316) and e.get('result')==0 and e.get('second_pathname')=='COMMITTED.json')['enter_ns']=0
            elif label=='wrong_final_links':
                parts=changed['final_backing_after']['identity'].split(':');parts[2]='2';changed['final_backing_after']['identity']=':'.join(parts)
            elif label=='changed_sync_event':next(e for e in changed['trace']['events'] if e['syscall'] in (74,75))['result']=-1
            elif label in ('failed_unlink','unlink_clock','wrong_name','remove_window'):
                event=next(e for e in changed['trace']['events'] if e['syscall']==263 and e.get('pathname')=='1.part')
                if label=='failed_unlink':event['result']=-1
                elif label=='unlink_clock':event['exit_ns']=changed['restore_started_ns']-1
                elif label=='remove_window':event['exit_ns']=changed['restore_started_ns']+1
                else:event['pathname']='data.bin'
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
    inputs['retained_fixture_failures']=[dict(run_id=failed['run_id'],file=failed_path.name,sha256=sha(failed_path.read_bytes()),reason=failed['reason'])]
    regression=subprocess.run([sys.executable,str(root/'scripts/test_nfs_rpc.py'),'-v'],capture_output=True,text=True,timeout=20)
    assert regression.returncode==0;inputs['decoder_regression']=dict(passed=True,output=regression.stdout+regression.stderr)
    for key,path in (('verifier',Path(__file__)),('storage_verifier',root/'scripts/verify-nfs-distinct-recovery.py'),('transitive_verifier',root/'scripts/verify-nfs-server-mover.py'),('native_verifier',root/'scripts/verify-nfs-server-recovery.py'),('gate_auditor',root/'scripts/check-rust-sles.py'),('inventory_collector',root/'scripts/capture-nfs-lab-inventory.py')):
        data=path.read_bytes();inputs[key]=dict(sha256=sha(data),base64=base64.b64encode(data).decode())
    raw=(args.live/'report.json').read_bytes()
    save('RUST-NFS-PUBLICATION-RECOVERY-EVIDENCE.json',dict(format='zlib-base64-json',report_sha256=sha(raw),report_zlib_base64=base64.b64encode(zlib.compress(raw,9)).decode()))
    save('RUST-NFS-PUBLICATION-RECOVERY-INPUT-EVIDENCE.json',inputs)
    save('RUST-SLES-EVIDENCE.json',gates['production']);save('RUST-SLES-QUALIFICATION-EVIDENCE.json',gates['qualification'])
    print(json.dumps(dict(run_id=live['run_id'],cases=summaries,native_controls=len(native_analysis),proof_controls=len(controls),storage_controls=len(storage_controls),verified_elf_count=count,cleanup_errors=[])))


if __name__=='__main__':main()
