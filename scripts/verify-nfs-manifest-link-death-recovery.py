#!/usr/bin/env python3
"""Audit coordinator-death manifest LINK recovery, exact builds and normal cleanup."""
import argparse
import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile
import shutil
import uuid
import zlib
from nfs_mount_profile import covering, parse
from nfs_rpc import call, reply


def sha(data):return hashlib.sha256(data).hexdigest()


def load_module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def analyze_database(record,original):
    assert record['observation']=='copied local database and existing WAL; no original SQLite opened'
    assert set(record['files'])=={'jobs.sqlite','jobs.sqlite-wal'}
    workspace=Path(__file__).resolve().parents[1]
    scratch=(workspace/'rust/validation').resolve();assert scratch.is_relative_to(workspace)
    folder=scratch/('bfm-manifest-proof-'+uuid.uuid4().hex)
    folder.mkdir()  # Inherit the writable workspace ACL; no global permission change.
    db=None
    try:
        assert folder.resolve().parent==scratch
        for name,item in record['files'].items():
            data=zlib.decompress(base64.b64decode(item['zlib_base64']));assert sha(data)==item['sha256']
            (folder/name).write_bytes(data)
        db=sqlite3.connect((folder/'jobs.sqlite').as_uri()+'?mode=ro',uri=True)
        db.execute('PRAGMA query_only=ON')
        manifest=db.execute('SELECT phase,bytes,sha256 FROM manifests WHERE job_id=1').fetchone()
        transfers=db.execute('SELECT file_index,attempt,phase FROM transfers WHERE job_id=1 ORDER BY file_index,attempt').fetchall()
    finally:
        if db is not None:db.close()
        assert folder.resolve().parent==scratch and folder.name.startswith('bfm-manifest-proof-')
        shutil.rmtree(folder)
    assert list(manifest)==record['manifest']==[3,original['bytes'],original['sha256']]
    assert [list(row) for row in transfers]==record['transfers']==[[0,1,4]]
    return dict(manifest_phase=3,payload_phase=4,attempt=1,reconstructed_from_raw_database=True)


def analyze(c):
    expected=sha(bytes(2097152)+b'0123456789abcdefg')
    assert c['passed'] and c['scenario_id']=='SC-130' and c['point']=='manifest_link_rpc'
    assert c['original_state_preserved'] and c['root_identities_stable'] and c['source_retained']
    assert c['handoff']['job_id']==c['replay']['job_id']=='1' and c['handoff']['source_paths_released'] and c['replay']['source_paths_released']
    assert c['source_backing_before']==c['source_backing_stopped']==c['orphan_source']==c['settlement_source']==c['source_backing_after']
    assert c['source_backing_before']['sha256']==expected
    assert c['destination_backing_before']==c['destination_backing_stopped']==c['orphan_staging']==c['manifest_final_after']
    stage=c['destination_backing_before'];original=c['manifest_staging_before']
    assert original==c['manifest_staging_stopped']==c['orphan_publication']
    assert original['manifest_absent'] and original['payload_staging_absent']
    assert stage==dict(identity=original['identity'],sha256=original['sha256'])
    assert stage['sha256']==sha(original['bytes'].encode()) and stage['identity'].split(':')[2:]==['1',str(len(original['bytes'].encode()))]
    assert json.loads(original['bytes'])==c['manifest']
    assert c['payload_before']==c['payload_stopped']==c['orphan_payload']==c['settlement_payload']==c['payload_after']
    assert c['payload_before']['sha256']==expected and c['payload_before']['identity'].split(':')[2:]==['1','2097169']
    assert c['settlement_payload_staging_absent']
    assert c['status_before']==c['status_during'] and c['status_before']['state']=='Claimed' and c['status_before']['details']['files'][0]['transfer_phase']=='Published' and c['status_before']['details']['manifest_phase']==3
    assert c['original_local_state']==c['local_state_during']==c['local_state_after'] and c['original_enrollment']==c['enrollment_after']
    devices=[c['original_source'][0].split(':')[0],c['staging_before'].split(':')[0],c['original_local_state'].splitlines()[0].split(':')[0]]
    assert len(set(devices))==3 and c['filesystem_types'][:2]==['6969','6969'] and c['filesystem_types'][2]!='6969'
    assert c['final_identity']==':'.join(c['staging_before'].split(':')[:2]) and c['staging_absent_after']
    assert c['worker_pid']==c['paused_worker']['pid'] and '--internal-delivery-worker' in c['paused_worker']['command']
    blocked=c['blocked_link'];fields=blocked['syscall'].split();parent=c['config']['destination_root']+'/1/.staging';final_parent=c['config']['destination_root']+'/1'
    assert blocked['state']=='D' and len(fields)==9 and fields[0]=='265' and int(fields[1],16)==blocked['fd'] and int(fields[3],16)==blocked['newfd'] and int(fields[5],16)==0
    assert blocked['path']==parent and blocked['newpath']==final_parent
    security=dict(line.split(':',1) for line in c['worker_security'].splitlines() if ':' in line)
    assert security['Uid'].split()==security['Gid'].split()==['1000']*4 and security['NoNewPrivs'].strip()=='1'
    assert all(int(security[k],16)==0 for k in ('CapInh','CapPrm','CapEff')) and c['health_seconds']<5
    assert c['guard_exit']==73 and c['contender']['exit_code']!=0 and c['contender']['seconds']<6
    assert 'local instance or surviving worker already owns state' in c['contender']['stderr'] and c['contender']['config']==dict(c['config'],bind='127.0.0.1:0')
    assert c['coordinator_exit_code']!=0 and c['coordinator_pid']!=c['coordinator_after'] and c['worker_exit'] in ('gone','Z')
    assert c['status_after_exit']['phase']=='NoActiveOwner' and c['coordinator_kill_ns']<c['restore_started_ns']<c['worker_exit_observed_ns']<c['restart_started_ns']
    assert len(c['orphan_samples'])==3
    for sample in c['orphan_samples']:
        assert sample['worker_state']==sample['worker_after']=='D' and sample['guard_exit'] in (0,73) and sample['status_exit']==2 and sample['status']['phase']=='OwnerUnavailable'
    assert {r['command'] for r in c['orphan_contenders']}=={'service','--initialize-source','--transfer-one'}
    for contender in c['orphan_contenders']:assert contender['exit_code']!=0 and contender['seconds']<6 and 'local instance or surviving worker already owns state' in contender['stderr']
    epoch=c['epoch_before'];assert c['epoch_during']==c['orphan_epoch']==epoch and epoch['group']==int(c['coordinator_pid'])
    new=c['replacement_epoch'];assert new['group']==int(c['coordinator_after'])!=epoch['group'] and all(new[k]==epoch[k] for k in ('version','boot','namespace','guard'))
    stage_observed,final_observed=c['settlement_stage'],c['settlement_final']
    assert c['settlement_manifest_absent']==(final_observed is None) and (stage_observed or final_observed)
    if final_observed:assert c['settlement_manifest_bytes']==original['bytes'] and json.loads(c['settlement_manifest_bytes'])==c['manifest']
    for observed in (stage_observed,final_observed):
        if observed:
            assert observed['sha256']==stage['sha256'] and observed['identity'].split(':')[:2]==stage['identity'].split(':')[:2]
            assert observed['identity'].split(':')[2:]==(['2',stage['identity'].split(':')[3]] if stage_observed and final_observed else ['1',stage['identity'].split(':')[3]])
    if stage_observed and final_observed:assert stage_observed==final_observed
    assert c['database_before_restore']==c['database_after_exit']
    db_proof=analyze_database(c['database_after_exit'],original)
    before,after=c['before_server'],c['after_server']
    for key in ('container','address','image','mounts','boot_id'):assert before[key]==after[key]
    assert before['threads']==after['threads']=='2' and len(set(c['clock_namespaces'].values()))==1
    if c['kind']=='nfsd':
        assert c['stopped_server']['threads']=='0'
        for key in ('pid','started_at','netns'):assert before[key]==after[key]
    else:
        assert c['quiesced_server']['threads']=='0' and c['quiesced_server']['pid']==before['pid'] and c['quiesced_server']['container']==before['container']
        assert c['stop_exit_code']==137 and c['stopped_container']['Status']=='exited' and not c['stopped_container']['Running'] and c['stopped_container']['Pid']==0
        assert before['pid']!=after['pid'] and before['started_at']!=after['started_at']
    trace=c['trace'];assert trace['passed'] and not trace.get('cleanup_error') and trace['pid']==int(c['worker_pid']) and trace['expected_exit']=='coordinator-death' and trace['exit_status'] in (9,256)
    assert trace['completion']=='orphan_exit_requires_independent_remote_reconciliation'
    assert trace['syncs']==[e for e in trace['events'] if e['syscall'] in (74,75)] and all(e.get('result')==0 for e in trace['syncs'])
    events=[e for e in trace['events'] if e['syscall']==265 and e.get('pathname')=='COMMITTED.part' and e.get('second_pathname')=='COMMITTED.json'];assert len(events)==1;event=events[0]
    assert event['enter_ns']<c['coordinator_kill_ns'] and event['args'][:5]==[int(x,16) for x in fields[1:6]]
    for descriptor,info,path in ((event['descriptor'],blocked['fdinfo'],parent),(event['second_directory'],blocked['newfdinfo'],final_parent)):
        fdinfo=dict(line.split(':',1) for line in info.splitlines());assert descriptor['path']==path and descriptor['filesystem']=='nfs4' and descriptor['mount_id']==fdinfo['mnt_id'].strip() and descriptor['inode']==int(fdinfo['ino'])
    if 'exit_ns' in event:assert event['enter_ns']<=event['exit_ns']<=c['worker_exit_observed_ns']
    wire=c['wire'];assert not wire['errors'] and not wire['trace_overflow'] and c['before_wire']['trace'] and wire['trace'][:len(c['before_wire']['trace'])]==c['before_wire']['trace']
    pending={};pairs=[];total=unknown=0
    for row in wire['trace']:
        data=zlib.decompress(base64.b64decode(row['payload_zlib_base64']));total+=len(data);assert sha(data)==row['sha256'] and int.from_bytes(data[:4],'big')==row['xid']
        try:decoded=(call if row['direction']=='call' else reply)(data)
        except ValueError:decoded=None
        assert decoded==row['decoded'];unknown+=decoded is None;key=row['connection'],row['xid']
        if row['direction']=='call':pending[key]=row
        elif key in pending:
            request=pending.pop(key);assert request['monotonic_ns']<=row['monotonic_ns'];pairs.append((request,row))
    assert total==wire['trace_bytes'] and total<=64*1048576 and len(wire['trace'])<=8192
    links=[];errors=[];post_restore_writes=[]
    for request,response in pairs:
        arg,ret=request['decoded'],response['decoded']
        if not arg or not ret:continue
        if ret['status']:errors.append(ret['status']);continue
        for op,res in zip(arg['operations'],ret['operations']):
            assert op['op']==res['op'] and res['status']==0
            if op['op']==38 and response['monotonic_ns']>=c['restore_started_ns']:post_restore_writes.append((request,response))
            if op['op']==11 and op['name']=='COMMITTED.json' and response['monotonic_ns']>=c['restore_started_ns']:
                handles=[o['filehandle_sha256'] for o in arg['operations'] if o['op']==22];assert len(handles)==2
                links.append(dict(request_ns=request['monotonic_ns'],reply_ns=response['monotonic_ns'],handles=handles,request_sha256=request['sha256'],reply_sha256=response['sha256']))
    assert not post_restore_writes,'completed payload and manifest bytes must not be rewritten'
    assert links,'no actual successful manifest LINK after restoration'
    original_links=[]
    if event.get('result')==0:
        assert event['enter_ns']<c['coordinator_kill_ns']<c['restore_started_ns']<event['exit_ns']<=c['worker_exit_observed_ns']
        original_links=[link for link in links if event['enter_ns']<=link['request_ns']<=link['reply_ns']<=event['exit_ns']]
        assert original_links,'no successful raw LINK inside original pending linkat interval'
    if trace['exit_status']==256:
        assert event.get('result')==0
        assert any(e['syscall']==1 and e.get('result')==-32 and e.get('descriptor') and e['descriptor']['path'].startswith('socket:') for e in trace['events']), 'normal error exit lacks observed closed-channel write'
    unlinks=[e for e in trace['events'] if e['syscall']==263 and e.get('descriptor') and e['descriptor']['path']==parent and e.get('pathname')=='COMMITTED.part' and e.get('result')==0]
    if stage_observed is None:
        assert final_observed and len(unlinks)==1 and event.get('result')==0
        unlink=unlinks[0];assert event['exit_ns']<=unlink['enter_ns']<=unlink['exit_ns']<=c['worker_exit_observed_ns']
        assert [e['path'] for e in trace['syncs'] if event['exit_ns']<=e['enter_ns']<=e['exit_ns']<=unlink['enter_ns']]==[final_parent+'/COMMITTED.json',final_parent]
        assert any(e['path']==parent and unlink['exit_ns']<=e['enter_ns']<=e['exit_ns']<=c['worker_exit_observed_ns'] for e in trace['syncs'])
        if trace['exit_status']==256:
            assert [e['path'] for e in trace['syncs']]==[final_parent+'/COMMITTED.json',final_parent,parent,final_parent+'/COMMITTED.json',parent,final_parent]
            assert all(e['enter_ns']>=unlink['exit_ns'] for e in trace['syncs'][2:])
    assert not any(e['syscall'] in (264,265,316) and e.get('result')==0 and e.get('second_pathname')=='data.bin' for e in trace['events'])
    committed=c['committed'];assert committed['state']=='Committed' and committed['details']['manifest_phase']==4 and not committed['details']['source_cleanup_enabled'] and committed['details']['files'][0]['attempt']==1
    assert [x.split()[0] for x in c['hashes']]==[expected,expected]
    manifest=c['manifest'];assert manifest['job_id']=='1' and manifest['generator_id']=='fixture' and manifest['submission_id']==c['config']['source_binding']['root_id']
    assert [(f['path'],f['size_bytes'],f['algorithm'],f['sha256']) for f in manifest['files']]==[('nested/data.bin',2097169,'sha256',expected)]
    return dict(profile=c['profile'],kind=c['kind'],pending_link=True,coordinator_killed=True,orphan_exclusion=True,original_attempt=1,devices=devices,
        old_worker_wait_status=trace['exit_status'],old_link_result=event.get('result'),old_link_return_observed='exit_ns' in event,old_sync_count=len(trace['syncs']),final_present_after_old_exit=c['settlement_final'] is not None,
        database=db_proof,post_restore_write_count=len(post_restore_writes),raw_records=len(wire['trace']),unknown_records=unknown,successful_links=links,original_pending_links=original_links,protocol_errors=errors,raw_guard_closed_samples=sum(s['guard_exit']==0 for s in c['orphan_samples']))


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
    assert live['manifest_link_death_recovery'] and live['manifest_link_recovery'] and not live['payload_link_death_recovery'] and not live['payload_link_recovery'] and not live['publication_recovery'] and not live['verification_recovery'] and not live['manifest_recovery']
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
        fdinfo=dict(line.split(':',1) for line in c['blocked_link']['fdinfo'].splitlines())
        assert int(fdinfo['mnt_id'])==covering(parse(live['inventory']),c['config']['destination_root'])['id']
        newinfo=dict(line.split(':',1) for line in c['blocked_link']['newfdinfo'].splitlines())
        assert int(newinfo['mnt_id'])==int(fdinfo['mnt_id'])
    summaries=[analyze(c) for c in cases];controls=[]
    for c in cases:
        changes={
            'source':lambda x:x['source_backing_stopped'].update(sha256='bad'),
            'stage':lambda x:x['destination_backing_stopped'].update(sha256='bad'),
            'guard':lambda x:x.update(guard_exit=0),
            'orphan_status':lambda x:x['orphan_samples'][0]['status'].update(phase='NoActiveOwner'),
            'orphan_state':lambda x:x['orphan_samples'][0].update(worker_after='Z'),
            'contender':lambda x:x['orphan_contenders'][0].update(stderr='Address already in use'),
            'early_restart':lambda x:x.update(restart_started_ns=x['restore_started_ns']-1),
            'old_exit':lambda x:x.update(worker_exit='D'),
            'epoch':lambda x:x['replacement_epoch'].update(group=x['epoch_before']['group']),
            'settlement':lambda x:(x['settlement_stage'] or x['settlement_final']).update(sha256='bad'),
            'manifest':lambda x:x['manifest']['files'][0].update(sha256='bad'),
            'attempt':lambda x:x['committed']['details']['files'][0].update(attempt=2),
            'inode':lambda x:x.update(final_identity='bad'),
            'wire':lambda x:x['wire']['trace'][-1].update(sha256='bad'),
            'trace':lambda x:x['trace'].update(pid=0),
            'old_link_name':lambda x:next(e for e in x['trace']['events'] if e['syscall']==265).update(second_pathname='wrong'),
            'old_link_clock':lambda x:next(e for e in x['trace']['events'] if e['syscall']==265).update(enter_ns=x['coordinator_kill_ns']+1),
            'old_link_mount':lambda x:next(e for e in x['trace']['events'] if e['syscall']==265)['second_directory'].update(mount_id='999'),
            'old_exit_signal':lambda x:x['trace'].update(exit_status=0),
            'settlement_manifest':lambda x:x.update(settlement_manifest_absent=not x['settlement_manifest_absent']),
            'payload_custody':lambda x:x['settlement_payload'].update(sha256='wrong'),
            'committed_phase':lambda x:x['committed']['details'].update(manifest_phase=3),
            'database_phase':lambda x:x['database_after_exit']['manifest'].__setitem__(0,4),
            'database_hash':lambda x:x['database_after_exit']['files']['jobs.sqlite'].update(sha256='wrong'),
            'missing_database_wal':lambda x:x['database_after_exit']['files'].pop('jobs.sqlite-wal'),
            'database_changed':lambda x:x['database_before_restore']['transfers'].__setitem__(0,[0,2,4]),
            'old_epoch':lambda x:x['orphan_epoch'].update(group=0),
            'restoration_order':lambda x:x.update(restore_started_ns=x['restart_started_ns']+1),
            'settlement_links':lambda x:(x['settlement_stage'] or x['settlement_final']).update(identity=':'.join((x['settlement_stage'] or x['settlement_final'])['identity'].split(':')[:2]+['9',(x['settlement_stage'] or x['settlement_final'])['identity'].split(':')[3]])),
            'syscall':lambda x:x['blocked_link'].update(syscall='0 0'),
            'local_state':lambda x:x.update(local_state_after='bad'),
            'early_manifest':lambda x:x['orphan_publication'].update(manifest_absent=False),
            'blocked_fd':lambda x:x['blocked_link'].update(newpath='bad'),
            'security':lambda x:x.update(worker_security=x['worker_security'].replace('NoNewPrivs:\t1','NoNewPrivs:\t0')),
        }
        if any(e['syscall']==265 and e.get('pathname')=='COMMITTED.part' and e.get('result')==0 for e in c['trace']['events']):
            changes['original_rpc_window']=lambda x:next(e for e in x['trace']['events'] if e['syscall']==265 and e.get('pathname')=='COMMITTED.part').update(exit_ns=x['restore_started_ns']+1)
        if c['settlement_stage'] is None:
            changes['missing_old_unlink']=lambda x:x['trace'].update(events=[e for e in x['trace']['events'] if not (e['syscall']==263 and e.get('pathname')=='COMMITTED.part')])
            changes['early_old_unlink']=lambda x:next(e for e in x['trace']['events'] if e['syscall']==263 and e.get('pathname')=='COMMITTED.part').update(enter_ns=0)
        if c['settlement_final']:
            changes['visible_manifest_bytes']=lambda x:x.update(settlement_manifest_bytes='{}')
        if c['trace']['exit_status']==256:
            changes['missing_channel_error']=lambda x:x['trace'].update(events=[e for e in x['trace']['events'] if not (e['syscall']==1 and e.get('result')==-32)])
        if c['trace']['syncs']:
            changes['old_sync_error']=lambda x:x['trace']['syncs'][0].update(result=-1)
        if c['kind']=='container':changes['unquiesced']=lambda x:x['quiesced_server'].update(threads='2')
        for label,change in changes.items():
            changed=copy.deepcopy(c);change(changed)
            try:analyze(changed)
            except (AssertionError,ValueError,KeyError):controls.append(dict(profile=c['profile'],kind=c['kind'],control=label,passed=True))
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
    inputs['database_audit_runtime']=dict(python=sys.version,sqlite=sqlite3.sqlite_version,scope='offline copied fixture snapshots only')
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
    initial_path=root/'docs/RUST-NFS-PAYLOAD-LINK-DEATH-RECOVERY-INITIAL-EVIDENCE.json'
    initial=read(initial_path);assert initial['status']=='FAILED_RETAINED'
    for item in initial['files'].values():assert sha(zlib.decompress(base64.b64decode(item['zlib_base64'])))==item['sha256']
    rejected=json.loads(zlib.decompress(base64.b64decode(initial['files']['report.json']['zlib_base64'])))
    assert rejected['status']=='FAILED' and rejected['rust_executed'] and not rejected['cleanup_errors'] and len(rejected['cases'])==4 and len(rejected['mover_cases'])==1
    old=rejected['mover_cases'][0];trace=json.loads(old['incomplete_trace'])
    assert not trace['passed'] and trace['exit_status']==256 and trace['syncs'] and all(x['result']==0 for x in trace['syncs'])
    assert all(x['status']['phase']=='OwnerUnavailable' and x['worker_state']==x['worker_after']=='D' for x in old['orphan_samples'])
    assert any(e['syscall']==265 and e.get('pathname')=='1.part' and e.get('result')==0 for e in trace['events'])
    for item in rejected['sources'].values():assert sha(base64.b64decode(item['base64']))==item['sha256']
    inputs['retained_fixture_failures'].append(dict(run_id=initial['run_id'],file=initial_path.name,sha256=sha(initial_path.read_bytes()),reason=initial['reason']))

    audit_failure_path=root/'docs/RUST-NFS-MANIFEST-LINK-DEATH-RECOVERY-AUDIT-INITIAL-EVIDENCE.json'
    failed_audit=read(audit_failure_path);assert failed_audit['status']=='FAILED_RETAINED'
    for item in failed_audit['files'].values():assert sha(zlib.decompress(base64.b64decode(item['zlib_base64'])))==item['sha256']
    prior_raw=zlib.decompress(base64.b64decode(failed_audit['files']['report.json']['zlib_base64']))
    prior_report=json.loads(prior_raw)
    assert prior_report['run_id']==failed_audit['run_id'] and prior_report['status']=='PASSED' and not prior_report['cleanup_errors']
    assert len(prior_report['mover_cases'])==4 and all(c['passed'] for c in prior_report['mover_cases'])
    if failed_audit['run_id']==live['run_id']:
        assert prior_raw==(args.live/'report.json').read_bytes(),'acquisition changed after audit rejection'
    prior_code=zlib.decompress(base64.b64decode(failed_audit['files']['verifier.py']['zlib_base64']))
    diagnostic=zlib.decompress(base64.b64decode(failed_audit['files']['diagnostic.txt']['zlib_base64']))
    assert b"TemporaryDirectory(prefix='bfm-manifest-proof-')" in prior_code and b'PermissionError' in diagnostic and b'jobs.sqlite' in diagnostic
    inputs['retained_fixture_failures'].append(dict(run_id=failed_audit['run_id'],file=audit_failure_path.name,sha256=sha(audit_failure_path.read_bytes()),reason='Windows sandbox default temporary-directory denial; unchanged passed acquisition retained'))

    regression=subprocess.run([sys.executable,str(root/'scripts/test_nfs_rpc.py'),'-v'],capture_output=True,text=True,timeout=20)
    assert regression.returncode==0;inputs['decoder_regression']=dict(passed=True,output=regression.stdout+regression.stderr)
    for key,path in (('verifier',Path(__file__)),('storage_verifier',root/'scripts/verify-nfs-distinct-recovery.py'),('transitive_verifier',root/'scripts/verify-nfs-server-mover.py'),('native_verifier',root/'scripts/verify-nfs-server-recovery.py'),('gate_auditor',root/'scripts/check-rust-sles.py'),('inventory_collector',root/'scripts/capture-nfs-lab-inventory.py')):
        data=path.read_bytes();inputs[key]=dict(sha256=sha(data),base64=base64.b64encode(data).decode())
    raw=(args.live/'report.json').read_bytes()
    save('RUST-NFS-MANIFEST-LINK-DEATH-RECOVERY-EVIDENCE.json',dict(format='zlib-base64-json',report_sha256=sha(raw),report_zlib_base64=base64.b64encode(zlib.compress(raw,9)).decode()))
    save('RUST-NFS-MANIFEST-LINK-DEATH-RECOVERY-INPUT-EVIDENCE.json',inputs)
    save('RUST-SLES-EVIDENCE.json',gates['production']);save('RUST-SLES-QUALIFICATION-EVIDENCE.json',gates['qualification'])
    print(json.dumps(dict(run_id=live['run_id'],cases=summaries,native_controls=len(native_analysis),proof_controls=len(controls),storage_controls=len(storage_controls),verified_elf_count=count,cleanup_errors=[])))


if __name__=='__main__':main()
