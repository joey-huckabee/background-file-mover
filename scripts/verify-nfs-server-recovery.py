#!/usr/bin/env python3
"""Independently audit native server-recovery capability, never mover recovery."""
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
from nfs_rpc import Xdr, call, reply
from nfs_mount_profile import covering, parse


def sha(data):return hashlib.sha256(data).hexdigest()


def analyze_case(c):
    assert c['passed'] and c['file_while_stopped']==c['before_file']
    assert c['before_file']['sha256']==sha(b'A'*4096) and c['after_file']['sha256']==sha(b'B'*4096)
    assert c['before_file']['identity']==c['after_file']['identity']
    assert c['before_file']['identity'].split(':')[-2:]==['1','4096']
    raw=c['blocked_syscall'].split()
    assert raw[0] in ('18','74') and int(raw[1],16)==c['fd'] and c['blocked_fd_path']==c['path']
    assert c['blocked_stat'].rsplit(') ',1)[1].split()[0]=='D'
    assert 'retained FD write/fsync/readback/identity passed' in c['probe_output']
    before,after=c['before_server'],c['after_server']
    assert before['container']==after['container'] and before['image']==after['image']
    assert before['mounts']==after['mounts'] and before['address']==after['address']
    assert before['boot_id']==after['boot_id'] and before['threads']==after['threads']=='2'
    if c['kind']=='nfsd':
        assert c['stopped_server']['threads']=='0'
        assert before['started_at']==after['started_at'] and before['pid']==after['pid'] and before['netns']==after['netns']
    else:
        assert not c['stopped_container']['Running'] and c['stopped_container']['Status']=='exited'
        assert c['stopped_container']['Pid']==0 and c['stop_exit_code']==137
        assert before['started_at']!=after['started_at'] and before['pid']!=after['pid']
    security=dict(line.split(':',1) for line in c['probe_security'].splitlines() if ':' in line)
    assert security['Uid'].split()==security['Gid'].split()==['1000']*4 and security['NoNewPrivs'].strip()=='1'
    assert all(int(security[k],16)==0 for k in ('CapInh','CapPrm','CapEff'))
    assert len(c['clock_namespaces'])==3 and len(set(c['clock_namespaces'].values()))==1
    trace=c['trace'];assert trace['passed'] and trace['exit_status']==0 and not trace.get('cleanup_error')
    assert len(trace['syncs'])==2 and all(s['syscall']==74 and s['result']==0 and s['path']==c['path'] for s in trace['syncs'])
    wire=c['wire'];assert not wire['trace_overflow'] and not wire['errors'] and len(wire['trace'])<=8192
    assert wire['trace'][:len(c['before_wire']['trace'])]==c['before_wire']['trace']
    pending={};pairs=[];total=0;unknown=0
    for index,row in enumerate(wire['trace']):
        data=zlib.decompress(base64.b64decode(row['payload_zlib_base64']));total+=len(data)
        assert sha(data)==row['sha256'] and int.from_bytes(data[:4],'big')==row['xid']
        try:decoded=(call if row['direction']=='call' else reply)(data)
        except ValueError:decoded=None
        assert decoded==row['decoded']
        unknown+=decoded is None
        key=row['connection'],row['xid']
        if row['direction']=='call':pending[key]=(row,index)
        elif key in pending:
            request,entry=pending.pop(key);assert request['monotonic_ns']<=row['monotonic_ns']
            pairs.append((request,row,entry))
    assert total==wire['trace_bytes'] and total<=64*1048576
    writes={};errors=[]
    for request,response,index in pairs:
        arg,ret=request['decoded'],response['decoded']
        if not arg or not ret:continue
        if ret['status']:
            errors.append(dict(status=ret['status'],operations=ret['operations'],request_sha256=request['sha256']))
            continue
        ops=arg['operations']
        if [o['op'] for o in ops] not in ([53,22,38],[53,22,38,9]):continue
        assert [o['op'] for o in ret['operations']]==[o['op'] for o in ops] and all(o['status']==0 for o in ret['operations'])
        w,result=ops[2],ret['operations'][2]
        assert w['offset']==0 and w['count']==result['count']==4096 and w['stable']==result['committed']==2
        label='initial' if w['data_sha256']==sha(b'A'*4096) else 'recovered' if w['data_sha256']==sha(b'B'*4096) else None
        assert label,'unexpected successful probe WRITE'
        if label=='initial':assert index<len(c['before_wire']['trace'])
        else:assert index>=len(c['before_wire']['trace']) and response['monotonic_ns']>=c['restore_started_ns']
        sequence=bytes.fromhex(ops[0]['sequence_hex']);assert len(sequence)==32
        # The summary decoder omits SEQUENCE result fields. Check the raw echo
        # before using its request's session as successful recovery evidence.
        x=Xdr(zlib.decompress(base64.b64decode(response['payload_zlib_base64'])))
        assert [x.uint() for _ in range(3)]==[response['xid'],1,0]
        x.uint();x.opaque();assert x.uint()==0 and x.uint()==0
        x.opaque();assert x.uint()==len(ops) and x.uint()==53 and x.uint()==0
        assert x.take(24)==sequence[:24]
        writes.setdefault(label,[]).append(dict(filehandle_sha256=ops[1]['filehandle_sha256'],
            session_id=sequence[:16].hex(),write_verifier=result['verifier_hex'],request_sha256=request['sha256'],reply_sha256=response['sha256']))
    assert set(writes)=={'initial','recovered'}
    assert len({w['filehandle_sha256'] for group in writes.values() for w in group})==1,'original filehandle changed'
    old_sessions={w['session_id'] for w in writes['initial']};new_sessions={w['session_id'] for w in writes['recovered']}
    old_verifiers={w['write_verifier'] for w in writes['initial']};new_verifiers={w['write_verifier'] for w in writes['recovered']}
    return dict(kind=c['kind'],role=c['role'],retained_filehandle=True,writes=writes,
        session_changed=old_sessions.isdisjoint(new_sessions),write_verifier_changed=old_verifiers.isdisjoint(new_verifiers),
        netns_changed=before['netns']!=after['netns'],kernel_boot_unchanged=True,
        protocol_errors=errors,unknown_records=unknown,raw_records=len(wire['trace']))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('live',type=Path);parser.add_argument('--production-gate',type=Path,required=True)
    parser.add_argument('--qualification-gate',type=Path,required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    def read(path):return json.loads(path.read_text(encoding='utf-8'))
    def save(name,data):(root/'docs'/name).write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8',newline='\n')
    live=read(args.live/'report.json')
    assert live['status']=='PASSED' and not live['cleanup_errors'] and not live['rust_executed']
    assert not live['production_nfs_enabled'] and not live['source_deletion_enabled'] and live['glibc']=='glibc 2.22'
    assert live['config']==read(root/'scripts/rust-platform.json')
    for name,item in live['sources'].items():
        data=base64.b64decode(item['base64']);assert sha(data)==item['sha256'] and data==(root/'scripts'/name).read_bytes()
    cases=live['cases'];assert len(cases)==4 and {(c['kind'],c['role']) for c in cases}=={(k,r) for k in ('nfsd','container') for r in ('source','destination')}
    mounts=[covering(parse(live['inventory']),'/tmp/recovery-'+r) for r in ('source','destination')]
    assert mounts[0]['id']!=mounts[1]['id'] and all(m['filesystem']=='nfs4' and m['super']['vers']=='4.1' and 'hard' in m['super'] and 'noac' not in m['super'] and 'sync' not in m['super'] and m['super']['sec']=='sys' for m in mounts)
    summaries=[analyze_case(c) for c in cases]
    assert all(c['before_server']['address']==c['after_server']['address']==live['static_server_address'] for c in cases)
    controls=[]
    for c in cases:
        for label in ('server_bytes','identity','fd','state','wire_hash','missing_recovered_write','missing_checkpoint','wrong_restore_clock','reply_session_echo'):
            changed=copy.deepcopy(c)
            if label=='server_bytes':changed['file_while_stopped']['sha256']='wrong'
            elif label=='identity':changed['after_file']['identity']='wrong'
            elif label=='fd':changed['blocked_syscall']='1 0'
            elif label=='state':changed['blocked_stat']=changed['blocked_stat'].replace(') D ',') R ',1)
            elif label=='wire_hash':changed['wire']['trace'][-1]['sha256']='wrong'
            elif label=='missing_checkpoint':changed['before_wire']['trace']=[]
            elif label=='wrong_restore_clock':changed['restore_started_ns']=2**63
            elif label=='reply_session_echo':
                row=next(r for r in reversed(changed['wire']['trace']) if r['direction']=='reply' and r['decoded'] and r['decoded']['status']==0 and any(o['op']==38 for o in r['decoded']['operations']))
                data=bytearray(zlib.decompress(base64.b64decode(row['payload_zlib_base64'])));x=Xdr(data)
                x.take(16);x.opaque();x.take(8);x.opaque();x.take(12)
                data[x.offset]^=1
                assert reply(data)==row['decoded'], 'control must target an omitted SEQUENCE result field'
                row.update(sha256=sha(data),payload_zlib_base64=base64.b64encode(zlib.compress(data)).decode())
            else:changed['wire']=copy.deepcopy(changed['before_wire'])
            try:analyze_case(changed)
            except (AssertionError,ValueError):controls.append(dict(kind=c['kind'],role=c['role'],name=label,passed=True))
            else:raise AssertionError('bad recovery proof accepted: '+label)
    helper=root/'scripts/check-rust-sles.py';spec=importlib.util.spec_from_file_location('gate_audit',helper)
    auditor=importlib.util.module_from_spec(spec);spec.loader.exec_module(auditor)
    binary=(args.live/'probe').read_bytes();assert sha(binary)==live['probe']['sha256'] and auditor.audit(live['probe']['elf_text'])==live['probe']['elf']
    current={p.relative_to(root/'rust').as_posix():p.read_bytes() for child in (root/'rust').iterdir() if child.name not in ('target','validation') for p in (child.rglob('*') if child.is_dir() else [child]) if p.is_file()}
    inputs=dict(live_run_id=live['run_id'],scope='native capability only; no Rust mover recovery cases',case_analysis=summaries,
                proof_negative_controls=controls,rust_input_count=len(current),rust_inputs={n:sha(d) for n,d in current.items()},gates={},
                probe_binary_base64=base64.b64encode(binary).decode())
    gates={};count=0
    for mode,folder,expected in (('production',args.production_gate,211),('qualification',args.qualification_gate,212)):
        gate=read(folder/'report.json');assert gate['status']=='PASSED' and not gate.get('cleanup_error')
        assert gate['config']==live['config'] and gate['build_mode']==('production' if mode=='production' else 'nfs-qualification')
        assert len(gate['dependencies'])==42 and len(gate['audit_negative_controls'])==6
        archive=(folder/'source.tar.gz').read_bytes();assert sha(archive)==gate['source_sha256']
        with tarfile.open(folder/'source.tar.gz') as tar:assert {m.name:tar.extractfile(m).read() for m in tar if m.isfile()}==current
        for profile in ('debug','release'):
            row=gate['profiles'][profile];assert row['tests_passed']==expected and len(row['artifacts'])==10
            for item in row['artifacts']:
                assert sha((folder/item['name']).read_bytes())==item['sha256']
                assert auditor.audit((folder/(item['name']+'.elf')).read_text(encoding='utf-8'))==item['elf'];count+=1
        gates[mode]=gate;inputs['gates'][mode]=dict(run_id=gate['run_id'],source_archive_base64=base64.b64encode(archive).decode(),source_sha256=gate['source_sha256'])
    inventory=read(args.live/'post-run-inventory.json');baseline=read(root/'docs/RUST-NFS-SOURCE-SYNC-INPUT-EVIDENCE.json')['post_run_inventory']
    for engine in ('default','rootful'):
        assert not inventory[engine]['containers'] and sorted(inventory[engine]['networks'])==sorted(baseline[engine]['networks'])
        assert sorted(inventory[engine]['volume_metadata'],key=lambda v:v['Name'])==sorted(baseline[engine]['volume_metadata'],key=lambda v:v['Name'])
    inputs.update(post_run_inventory=inventory,verified_elf_count=count,source_snapshot_count=len(live['sources']))
    inputs['retained_failed_attempts']=[]
    for suffix in ('INITIAL','SECOND'):
        initial_path=root/('docs/RUST-NFS-SERVER-RECOVERY-'+suffix+'-EVIDENCE.json')
        initial=read(initial_path);assert initial['status']=='FAILED_RETAINED' and initial['run_id']!=live['run_id']
        for name,item in initial['files'].items():assert sha(zlib.decompress(base64.b64decode(item['zlib_base64'])))==item['sha256']
        rejected=json.loads(zlib.decompress(base64.b64decode(initial['files']['report.json']['zlib_base64'])))
        assert rejected['status']=='FAILED' and rejected['cleanup_errors'] and len(rejected['sources'])==9
        for item in rejected['sources'].values():assert sha(base64.b64decode(item['base64']))==item['sha256']
        rescue=json.loads(zlib.decompress(base64.b64decode(initial['files']['rescue-and-cleanup.json']['zlib_base64'])))
        assert not rescue['rootful_containers_after']
        inputs['retained_failed_attempts'].append(dict(run_id=initial['run_id'],retained_file=initial_path.name,sha256=sha(initial_path.read_bytes()),reason=initial['reason']))
    regression=subprocess.run([sys.executable,str(root/'scripts/test_nfs_rpc.py'),'-v'],capture_output=True,text=True,timeout=20)
    assert regression.returncode==0;inputs['decoder_regression']=dict(passed=True,output=regression.stdout+regression.stderr)
    for key,path in (('verifier',Path(__file__)),('gate_auditor',helper),('inventory_collector',root/'scripts/capture-nfs-lab-inventory.py')):
        data=path.read_bytes();inputs[key]=dict(sha256=sha(data),base64=base64.b64encode(data).decode())
    raw=(args.live/'report.json').read_bytes()
    save('RUST-NFS-SERVER-RECOVERY-EVIDENCE.json',dict(format='zlib-base64-json',report_sha256=sha(raw),report_zlib_base64=base64.b64encode(zlib.compress(raw,9)).decode()))
    save('RUST-NFS-SERVER-RECOVERY-INPUT-EVIDENCE.json',inputs)
    save('RUST-SLES-EVIDENCE.json',gates['production']);save('RUST-SLES-QUALIFICATION-EVIDENCE.json',gates['qualification'])
    print(json.dumps(dict(run_id=live['run_id'],cases=summaries,proof_controls=len(controls),verified_elf_count=count,cleanup_errors=[])))


if __name__=='__main__':main()
