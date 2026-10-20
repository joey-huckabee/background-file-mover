#!/usr/bin/env python3
"""Independently check COMMIT/UNSTABLE withholding, recovery and SLES inputs."""
import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import zlib
from nfs_rpc import call as decode_call, reply as decode_reply
from nfs_sync_capability import validate_resend, validate_unstable_resend, payload_resends
from nfs_io_analysis import analyze
from nfs_mount_profile import parse, covering


def sha(data):
    return hashlib.sha256(data).hexdigest()


def held_success(state, operation=5):
    assert state['armed'] and state['operation']==operation and state['held']
    assert not state['released'] and not state['dropped'] and not state['forwarded'] and not state['errors']
    for row in state['held']:
        request=bytes.fromhex(row['request']['payload_hex']);reply=bytes.fromhex(row['payload_hex'])
        assert sha(request)==row['request']['sha256'] and sha(reply)==row['reply_sha256']
        call=decode_call(request);result=decode_reply(reply)
        assert call==row['request']['decoded'] and result==row['reply']
        assert call['xid']==row['xid']==result['xid'] and result['status']==0
        selected=[op for op in call['operations'] if op['op']==operation]
        assert len(selected)==1
        response=next(op for op in result['operations'] if op['op']==operation)
        assert response['status']==0
        if operation==5:
            assert selected[0]['offset']==selected[0]['count']==0
        else:
            op=selected[0];data=bytes(2*1048576)+b'0123456789abcdefg'
            assert op['stable']==response['committed']==0 and op['count']==response['count']
            assert 0<=op['offset']<len(data) and op['count']>0 and op['offset']+op['count']<=len(data)
            assert sha(data[op['offset']:op['offset']+op['count']])==op['data_sha256']



def wire_check(wire):
    assert not wire['trace_overflow'] and not wire['errors']
    assert len(wire['trace'])<=8192 and wire['trace_bytes']<=64*1048576
    total=0
    for row in wire['trace']:
        data=zlib.decompress(base64.b64decode(row['payload_zlib_base64']))
        assert sha(data)==row['sha256'];total+=len(data)
        try:decoded=(decode_call if row['direction']=='call' else decode_reply)(data)
        except (ValueError,UnicodeError):decoded=None
        assert decoded==row['decoded']
    assert total==wire['trace_bytes']


def unstable_before_commit(row):
    """Correlate successful UNSTABLE ranges on the held COMMIT's handle.

    This is protocol evidence in the controlled window, not a global NAS
    identity or a unique kernel-causality claim.
    """
    wire=row['wires'][row['relay_role']]
    held=row['held']['held'][0]
    operations=held['request']['decoded']['operations']
    handles=[op['filehandle_sha256'] for op in operations if op['op']==22]
    assert len(handles)==1
    verifier=next(op['verifier_hex'] for op in held['reply']['operations'] if op['op']==5)
    anchor=next(r for r in wire['trace'] if r['direction']=='call' and r['connection']==held['connection']
                and r['sha256']==held['request']['sha256'])
    writes=[]
    for call in wire['trace']:
        if call['direction']!='call' or not call['decoded'] or call['monotonic_ns']>anchor['monotonic_ns']:continue
        ops=call['decoded']['operations']
        if [op['op'] for op in ops]!=[53,22,38] or ops[1]['filehandle_sha256']!=handles[0]:continue
        replies=[r for r in wire['trace'] if r['direction']=='reply' and r['connection']==call['connection']
                 and r['xid']==call['xid'] and r['decoded'] and r['decoded']['status']==0
                 and call['monotonic_ns']<=r['monotonic_ns']<=anchor['monotonic_ns']]
        assert replies
        op=ops[2];result=next(o for o in replies[0]['decoded']['operations'] if o['op']==38)
        assert op['count']==result['count'] and result['verifier_hex']==verifier
        if op['stable']!=0 or result['committed']!=0:continue
        offset,count=op['offset'],op['count']
        data=bytes(2*1048576)+b'0123456789abcdefg'
        assert offset+count<=len(data) and sha(data[offset:offset+count])==op['data_sha256']
        writes.append(dict(offset=offset,count=count,data_sha256=op['data_sha256']))
    assert writes,'no witnessed successful UNSTABLE range before held COMMIT'
    return dict(filehandle_sha256=handles[0],verifier_hex=verifier,unstable_ranges=writes)


def held_writes(row):
    held=row['before_release_or_drop']['held']
    handles=set();verifiers=set();ranges=set()
    for item in held:
        ops=item['request']['decoded']['operations']
        assert [o['op'] for o in ops]==[53,22,38]
        handles.add(ops[1]['filehandle_sha256'])
        op=ops[-1];ranges.add((op['offset'],op['count'],op['data_sha256']))
        result=next(o for o in item['reply']['operations'] if o['op']==38)
        verifiers.add(result['verifier_hex'])
    data=bytes(2*1048576)+b'0123456789abcdefg'
    expected={(offset,count,sha(data[offset:offset+count])) for offset,count in ((0,1048576),(1048576,1048576),(2097152,17))}
    assert len(handles)==len(verifiers)==1 and ranges==expected
    return dict(filehandle_sha256=next(iter(handles)),verifier_hex=next(iter(verifiers)),
                held_unstable_ranges=[dict(offset=o,count=n,data_sha256=h) for o,n,h in sorted(ranges)])


def complete_unstable_ranges(protocol):
    data=bytes(2*1048576)+b'0123456789abcdefg'
    actual={(r['offset'],r['count'],r['data_sha256']) for r in protocol['unstable_ranges']}
    expected={(o,n,sha(data[o:o+n])) for o,n in ((0,1048576),(1048576,1048576),(2097152,17))}
    assert actual==expected


def live_recovery(c):
    samples=c['live_recovery_samples'];assert samples and c['coordinator_pid'].isdigit()
    assert samples[-1]['status']['state']=='Committed'
    elapsed=-1
    for sample in samples:
        assert sample['elapsed_seconds']>=elapsed;elapsed=sample['elapsed_seconds']
        assert sample['health_code']==sample['status_code']==200
        assert sample['health_seconds']<5 and sample['status_seconds']<5
        assert sample['coordinator_pid']==c['coordinator_pid']
        assert set(sample['children'])<=set([c['paused_worker']['pid']])
        assert sample['status']['details']['files'][0]['attempt']==1
        assert sample['status']['details']['condition']!='ReviewRequired'
        replay=sample['replay'];assert replay[0]==202 and replay[1]['job_id']=='1' and replay[1]['source_paths_released']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('live',type=Path)
    parser.add_argument('--production-gate',required=True,type=Path)
    parser.add_argument('--qualification-gate',required=True,type=Path)
    parser.add_argument('--unstable',action='store_true',help='Audit the separate UNSTABLE WRITE matrix')
    parser.add_argument('--live-loss',action='store_true',help='Audit live coordinator recovery without death')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    operation=38 if args.unstable else 5
    slug='unstable' if args.unstable else 'commit'
    scenario='SC-114' if args.live_loss else ('SC-113' if args.unstable else 'SC-112')
    matrix='buffered-'+slug+('-live-loss' if args.live_loss else '')
    case_count=4 if args.live_loss else 8
    actions=('live-drop',) if args.live_loss else ('live-release','death-drop')
    prefix='RUST-NFS-BUFFERED-'+slug.upper()+('-LIVE-LOSS' if args.live_loss else '')
    def read(path):return json.loads(path.read_text(encoding='utf-8'))
    def save(name,value):(root/'docs'/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')
    current={p.relative_to(root/'rust').as_posix():p.read_bytes()
             for child in (root/'rust').iterdir() if child.name not in ('target','validation')
             for p in (child.rglob('*') if child.is_dir() else [child]) if p.is_file()}
    live=read(args.live/'report.json');auth=live['authorization']
    assert live['status']=='PASSED' and not live['cleanup_errors'] and live['rust_executed']
    assert live['glibc']=='glibc 2.22' and live['config']==read(root/'scripts/rust-platform.json')
    assert not live['production_nfs_enabled'] and not live['source_deletion_enabled']
    assert live['observer_capabilities']==['SYS_PTRACE','DAC_READ_SEARCH']
    client=dict(line.split(':',1) for line in live['client_security'].splitlines() if ':' in line)
    assert all(int(client[k],16)==((1<<21)|(1<<19)|(1<<2)) for k in ('CapPrm','CapEff','CapBnd'))
    assert int(client['CapInh'],16)==int(client['CapAmb'],16)==0 and client['NoNewPrivs'].strip()=='1'
    assert auth['passed'] and auth['matrix']==matrix
    assert len(live['checks'])==43 and all(c['passed'] for c in live['checks'])
    if args.unstable:assert len(live['sources'])==26
    assert len(live['sources']) in (25,26)
    if args.unstable or args.live_loss:assert auth['write_resend_tests']['passed']
    for name,item in live['sources'].items():
        data=base64.b64decode(item['base64'])
        assert sha(data)==item['sha256'] and data==(root/'scripts'/name).read_bytes()
    for relay in auth['relays'].values():
        sec=dict(line.split(':',1) for line in relay['security'].splitlines() if ':' in line)
        assert sec['Uid'].split()==sec['Gid'].split()==['1000']*4 and sec['NoNewPrivs'].strip()=='1'
        assert all(int(sec[k],16)==0 for k in ('CapInh','CapPrm','CapEff'))
        assert not relay['final_state']['errors'] and not relay['final_state']['armed'] and not relay['ports_published']
    assert tuple(map(int,auth['probe']['elf']['maximum_glibc'][6:].split('.'))) <= (2,22)
    assert auth['probe']['elf']['interpreter']==live['config']['interpreter']
    assert set(auth['probe']['elf']['libraries'])<=set(live['config']['allowed_libraries'])
    expected=sha(bytes(2*1048576)+b'0123456789abcdefg')
    def check_pending(row):
        held_success(row['held'],operation);held_success(row['before_release_or_drop'],operation)
        pending=row['pending'];sysargs=pending['syscall'].split()
        assert sysargs[0]=='91' and int(sysargs[1],16)==pending['fd'] and int(sysargs[2],16)==0o400
        assert pending['state']=='D' and pending['path']==row['target']
        obj=row['server_while_withheld']
        assert obj['sha256']==expected and obj['nfsd_threads']=='2'
        assert int(obj['identity'].split(':')[3])==2*1048576+17
        fdinfo=dict(line.split(':',1) for line in pending['fdinfo'].splitlines() if ':' in line)
        assert int(fdinfo['ino'])==int(obj['identity'].split(':')[1])
        settled=row['settled'];action='drop' if row['action'] in ('drop','death-drop','live-drop') else 'release'
        assert not settled['armed'] and not settled['errors']
        actual=settled['dropped' if action=='drop' else 'released']
        assert actual and all(item in actual for item in row['before_release_or_drop']['held'])
        assert not settled['released' if action=='drop' else 'dropped']
        if action=='drop':assert settled['connection_resets']
        for wire in row['wires'].values():wire_check(wire)
        protocol=held_writes(row) if args.unstable else unstable_before_commit(row)
        if args.live_loss and not args.unstable:complete_unstable_ranges(protocol)
        return protocol
    caps=auth['capabilities'];assert len(caps)==2
    assert {c['layout'] for c in caps}=={'same-share','separate-shares'}
    for cap in caps:
        assert cap['passed'] and [p['action'] for p in cap['probes']]==['discovery','release','drop']
        for row in cap['probes']:
            assert row['passed'] and 'fchmod returned 0' in row['output'] and 'fsync returned 0' in row['output']
            for wire in row['wires'].values():wire_check(wire)
            if row['action']=='discovery':
                assert len(row['clock_namespaces'])==(3 if cap['layout']=='same-share' else 4)
                assert len(set(row['clock_namespaces'].values()))==1
                trace=row['trace'];analysis=analyze(trace,row['wires']);assert analysis==row['analysis']
                assert trace['passed']
                commits=[r for r in analysis['rpc_operations'] if r['operation']['op']==operation]
                assert commits
                for request in commits:
                    assert any(trace['events'][i]['syscall']==91 and trace['events'][i]['result']==0
                               and trace['events'][i]['descriptor']['path']==row['target'] for i in request['overlapping_events'])
                    if args.unstable:
                        assert request['operation']['stable']==0
                        replies=[r for r in row['wires'][request['relay_role']]['trace'] if r['direction']=='reply'
                                 and r['connection']==request['connection'] and r['xid']==request['xid'] and r['decoded']]
                        assert any(r['decoded']['status']==0 and any(op['op']==38 and op['status']==0
                                   and op['committed']==0 and op['count']==request['operation']['count']
                                   for op in r['decoded']['operations']) for r in replies)
            else:
                check_pending(row)
                assert row['server_after']==row['server_while_withheld']
                if row['action']=='drop':
                    assert (validate_unstable_resend(row) if args.unstable else validate_resend(row,5))==row['resend_validation']
                    wire=row['wires'][row['relay_role']]
                    for forwarded in row['wire']['forwarded']:
                        raw=bytes.fromhex(forwarded['payload_hex'])
                        assert sha(raw)==forwarded['reply_sha256'] and decode_reply(raw)==forwarded['reply']
                        request=bytes.fromhex(forwarded['request']['payload_hex'])
                        assert sha(request)==forwarded['request']['sha256'] and decode_call(request)==forwarded['request']['decoded']
                        assert any(r['direction']=='call' and r['connection']==forwarded['connection'] and r['sha256']==sha(request) for r in wire['trace'])
                        assert any(r['direction']=='reply' and r['connection']==forwarded['connection'] and r['sha256']==sha(raw) for r in wire['trace'])
    cases=auth['cases'];assert len(cases)==case_count
    assert {(c['layout'],c['profile'],c['action']) for c in cases}=={
        (layout,profile,action) for layout in ('same-share','separate-shares') for profile in ('debug','release')
        for action in actions}
    summaries=[]
    for c in cases:
        assert c['passed'] and c['source_and_state_preserved'] and c['source_retained']
        assert c['scenario_id']==scenario
        assert c['binary_sha256']==auth['gates']['qualification']['artifacts'][c['profile']]['sha256']
        assert c['filesystem_types'][:2]==['6969','6969'] and c['filesystem_types'][2]!='6969'
        assert c['root_identities_stable']
        assert all(c['config'][role+'_binding']['nfs_mount']['profile']=='NMP-41B' for role in ('source','destination'))
        target=c['config']['destination_root']+'/1/.staging/1.part'
        protocol=check_pending(dict(c,target=target))
        sec=dict(line.split(':',1) for line in c['worker_security'].splitlines() if ':' in line)
        assert sec['Uid'].split()==sec['Gid'].split()==['1000']*4
        assert sec['NoNewPrivs'].strip()=='1' and all(int(sec[k],16)==0 for k in ('CapInh','CapPrm','CapEff'))
        mounts=[covering(parse(c['inventory']),c['config'][role+'_root']) for role in ('source','destination')]
        assert (mounts[0]==mounts[1])==(c['layout']=='same-share')
        assert all('noac' not in m['super'] and 'sync' not in m['super'] for m in mounts)
        assert c['during']['details']['files']==c['before']['details']['files'] and c['health_seconds']<5
        assert c['source_identity_after']==c['original_source'][0] and c['original_source'][1].split()[0]==expected
        assert c['database_before']==c['database_after'] and c['enrollment_before']==c['enrollment_after']
        assert c['accepted'][0]==c['replay'][0]==202 and c['accepted'][1]['job_id']==c['replay'][1]['job_id']=='1'
        assert c['accepted'][1]['source_paths_released'] and c['replay'][1]['source_paths_released']
        assert c['committed']['state']=='Committed' and not c['committed']['details']['source_cleanup_enabled']
        assert c['manifest']['version']==1 and c['manifest']['job_id']=='1' and c['manifest']['generator_id']=='fixture'
        assert [(f['path'],f['size_bytes'],f['algorithm'],f['sha256']) for f in c['manifest']['files']]==[('nested/data.bin',2*1048576+17,'sha256',expected)]
        assert [line.split()[0] for line in c['hashes']]==[expected,expected]
        death=c['action']=='death-drop'
        assert c['committed']['details']['files'][0]['attempt']==(2 if death else 1)
        if args.live_loss:
            live_recovery(c)
            selected,scope=payload_resends(c,operation)
            assert scope==c['resend_scope']
            assert (validate_unstable_resend(selected) if args.unstable else validate_resend(selected,5))==c['resend_validation']
            wire=c['wires'][c['relay_role']]
            for forwarded in c['wire']['forwarded']:
                raw=bytes.fromhex(forwarded['payload_hex']);request=bytes.fromhex(forwarded['request']['payload_hex'])
                assert sha(raw)==forwarded['reply_sha256'] and decode_reply(raw)==forwarded['reply']
                assert sha(request)==forwarded['request']['sha256'] and decode_call(request)==forwarded['request']['decoded']
                assert any(r['direction']=='call' and r['connection']==forwarded['connection'] and r['sha256']==sha(request) for r in wire['trace'])
                assert any(r['direction']=='reply' and r['connection']==forwarded['connection'] and r['sha256']==sha(raw) for r in wire['trace'])
            protocol['resend_validation']=c['resend_validation']
        if death:
            if args.unstable:assert c['coordinator_exit']!=0 and c['coordinator_pid'].isdigit()
            assert c['worker_exit'] in ('gone','Z')
            assert c['orphan_guard_probe']['exit_code']==73 and c['orphan_guard_probe']['worker_state']=='D'
            assert c['preserved_partial']==c['server_after_exit']==c['server_while_withheld']
        summaries.append(dict(layout=c['layout'],profile=c['profile'],action=c['action'],relay_role=c['relay_role'],
                              attempt=c['committed']['details']['files'][0]['attempt'],protocol=protocol,passed=True))
    controls=[];sample=caps[0]['probes'][1]['held']
    for label in ('unarmed','forwarded','wrong_operation','reply_corrupted','request_corrupted',
                  'rehashed_reply_xid','rehashed_request_xid'):
        value=copy.deepcopy(sample)
        if label=='unarmed':value['armed']=False
        elif label=='forwarded':value['forwarded']=value['held']
        elif label=='wrong_operation':value['operation']=5 if args.unstable else 38
        elif label=='reply_corrupted':value['held'][0]['payload_hex']=bytes([int(value['held'][0]['payload_hex'][:2],16)^1]).hex()+value['held'][0]['payload_hex'][2:]
        elif label=='request_corrupted':value['held'][0]['request']['payload_hex']=bytes([int(value['held'][0]['request']['payload_hex'][:2],16)^1]).hex()+value['held'][0]['request']['payload_hex'][2:]
        else:
            item=value['held'][0]
            target=item if label=='rehashed_reply_xid' else item['request']
            raw=bytearray.fromhex(target['payload_hex']);raw[0]^=1;target['payload_hex']=raw.hex()
            if label=='rehashed_reply_xid':
                item['reply_sha256']=sha(raw);item['reply']=decode_reply(raw)
            else:
                target['sha256']=sha(raw);target['decoded']=decode_call(raw)
        try:held_success(value,operation)
        except (AssertionError,ValueError):controls.append(dict(name=label,passed=True))
        else:raise AssertionError('negative control accepted: '+label)
    if args.unstable:
        for label in ('omitted_unstable_range','foreign_unstable_handle','mixed_write_verifier','wrong_range_bytes'):
            value=copy.deepcopy(caps[0]['probes'][1])
            held=value['before_release_or_drop']['held']
            if label=='omitted_unstable_range':
                value['before_release_or_drop']['held']=[r for r in held if r['request']['decoded']['operations'][-1]['offset']!=0]
            elif label=='foreign_unstable_handle':held[0]['request']['decoded']['operations'][1]['filehandle_sha256']='foreign'
            elif label=='mixed_write_verifier':next(o for o in held[0]['reply']['operations'] if o['op']==38)['verifier_hex']='other'
            else:held[0]['request']['decoded']['operations'][-1]['data_sha256']='other'
            try:held_writes(value)
            except AssertionError:controls.append(dict(name=label,passed=True))
            else:raise AssertionError('negative range control accepted: '+label)
    if args.live_loss and not args.unstable:
        original=unstable_before_commit(caps[0]['probes'][1])
        for label in ('missing_precommit_range','overlapping_precommit_range'):
            value=copy.deepcopy(original)
            if label=='missing_precommit_range':value['unstable_ranges'].pop()
            else:value['unstable_ranges'][-1]['offset']=0
            try:complete_unstable_ranges(value)
            except AssertionError:controls.append(dict(name=label,passed=True))
            else:raise AssertionError('incomplete pre-COMMIT coverage accepted: '+label)
    if args.live_loss:
        for label in ('changed_coordinator','replacement_worker','second_attempt','review_required',
                      'lost_202','slow_health','not_committed','no_samples'):
            value=copy.deepcopy(cases[0]);sample=value['live_recovery_samples'][-1]
            if label=='changed_coordinator':sample['coordinator_pid']='different'
            elif label=='replacement_worker':sample['children']=['different']
            elif label=='second_attempt':sample['status']['details']['files'][0]['attempt']=2
            elif label=='review_required':sample['status']['details']['condition']='ReviewRequired'
            elif label=='lost_202':sample['replay'][0]=503
            elif label=='slow_health':sample['health_seconds']=5
            elif label=='not_committed':sample['status']['state']='Pending'
            else:value['live_recovery_samples']=[]
            try:live_recovery(value)
            except AssertionError:controls.append(dict(name=label,passed=True))
            else:raise AssertionError('negative live control accepted: '+label)
    inputs=dict(live_run_id=live['run_id'],matrix=matrix,rust_input_count=len(current),
                rust_inputs={name:sha(data) for name,data in current.items()},gates={},case_analysis=summaries,
                withholding_negative_controls=controls)
    if args.live_loss:
        inputs['selector_negative_controls']=[]
        for flags,reason in ((['--live-loss'],'live-loss requires a payload reply matrix'),
                             (['--same-share','--live-loss'],'live-loss requires a payload reply matrix'),
                             (['--buffered-commit','--live-loss'],'buffered-commit requires both gates'),
                             (['--buffered-unstable','--live-loss'],'buffered-unstable requires both gates')):
            checked=subprocess.run([sys.executable,str(root/'scripts/check-nfs-mount-profile.py'),*flags],
                                   capture_output=True,text=True,timeout=20)
            output=checked.stdout+checked.stderr
            assert checked.returncode!=0 and reason in output and 'Mount-profile validation:' not in output
            inputs['selector_negative_controls'].append(dict(flags=flags,exit_code=checked.returncode,output=output,passed=True))
    probe=auth['probe'];binary=(args.live/'nfs-sync-probe').read_bytes()
    assert sha(binary)==probe['sha256'] and binary.startswith(b'\x7fELF')
    assert probe['source_sha256']==sha((root/'scripts/nfs_sync_probe.c').read_bytes())
    inputs['fixture_probe']=dict(**probe,binary_base64=base64.b64encode(binary).decode())
    auditor=(root/'scripts/check-rust-sles.py').read_bytes()
    inputs['probe_auditor']=dict(path='scripts/check-rust-sles.py',sha256=sha(auditor),base64=base64.b64encode(auditor).decode())
    inputs['python_regressions']={}
    for name in ('test_nfs_rpc.py','test_nfs_io_analysis.py',*(['test_nfs_write_resend.py'] if args.unstable or args.live_loss else [])):
        tested=subprocess.run([sys.executable,str(root/'scripts'/name),'-v'],capture_output=True,text=True,timeout=20)
        assert tested.returncode==0
        inputs['python_regressions'][name]=dict(passed=True,output=tested.stdout+tested.stderr)
    gates = {}
    count = 0
    for mode, folder, expected in (('production', args.production_gate, 211), ('qualification', args.qualification_gate, 212)):
        data = read(folder/'report.json')
        assert data['status'] == 'PASSED' and not data.get('cleanup_error')
        assert data['config'] == read(root/'scripts/rust-platform.json')
        assert data['build_mode'] == ('production' if mode == 'production' else 'nfs-qualification')
        assert len(data['dependencies']) == 42 and len(data['audit_negative_controls']) == 6
        archive = (folder/'source.tar.gz').read_bytes()
        assert sha(archive) == data['source_sha256']
        with tarfile.open(folder/'source.tar.gz') as tar:
            assert {m.name: tar.extractfile(m).read() for m in tar if m.isfile()} == current
        native = live['authorization']['gates'][mode]
        prior = read(root/'rust/validation'/native['run_id']/'report.json')
        assert prior['status'] == 'PASSED' and not prior.get('cleanup_error')
        assert prior['source_sha256'] == native['source_sha256']
        prior_archive = root/'rust/validation'/native['run_id']/'source.tar.gz'
        assert sha(prior_archive.read_bytes()) == native['source_sha256']
        with tarfile.open(prior_archive) as tar:
            assert {m.name: tar.extractfile(m).read() for m in tar if m.isfile()} == current
        for profile in ('debug', 'release'):
            item = data['profiles'][profile]
            assert item['tests_passed'] == expected and len(item['artifacts']) == 10
            assert [a['sha256'] for a in item['artifacts']] == [a['sha256'] for a in prior['profiles'][profile]['artifacts']]
            shipping = next(a for a in item['artifacts'] if not a['test'])
            assert shipping['sha256'] == native['artifacts'][profile]['sha256']
            for artifact in item['artifacts']:
                assert sha((folder/artifact['name']).read_bytes()) == artifact['sha256']
                count += 1
        gates[mode] = data
        inputs['gates'][mode] = dict(run_id=data['run_id'], source_sha256=data['source_sha256'],
            source_archive_base64=base64.b64encode(archive).decode(), byte_identical_artifacts_to_live_gate=native['run_id'], artifact_count=20)
    inputs.update(verified_elf_count=count, source_snapshot_count=len(live['sources']),
                  all_driver_snapshots_match_current=True)
    inventory = read(args.live/'post-run-inventory.json')
    assert not inventory['default']['containers'] and not inventory['rootful']['containers']
    assert set(inventory['rootful']['volumes']) == {'file-mover-rustup-1-99','file-mover-cargo-registry'}
    assert inventory['rootful']['networks'] == ['podman']
    inputs['post_run_inventory'] = inventory
    if args.live_loss:
        preliminary_path=root/'docs/RUST-NFS-BUFFERED-LIVE-LOSS-PRELIMINARY-EVIDENCE.json'
        preliminary=read(preliminary_path)
        raw=zlib.decompress(base64.b64decode(preliminary['report_zlib_base64']))
        assert sha(raw)==preliminary['report_sha256'] and preliminary['qualification_status']=='PASSED'
        prior=json.loads(raw)
        assert prior['status']=='PASSED' and not prior['cleanup_errors'] and prior['run_id']!=live['run_id']
        assert prior['authorization']['matrix']=='buffered-commit-live-loss'
        assert len(prior['authorization']['cases'])==4 and all(c['passed'] for c in prior['authorization']['cases'])
        assert len(prior['sources'])==26 and set(prior['sources'])==set(live['sources'])
        changed=[]
        for name,item in prior['sources'].items():
            assert sha(base64.b64decode(item['base64']))==item['sha256']
            if item['sha256']!=live['sources'][name]['sha256']:changed.append(name)
        assert set(changed)=={'nfs_buffered_commit.py','nfs_sync_capability.py','test_nfs_write_resend.py'}
        inputs['preliminary_acquisition']=dict(run_id=prior['run_id'],status='PASSED',
            retained_file=preliminary_path.name,report_sha256=preliminary['report_sha256'],
            final_common_source_changes=changed,reason=preliminary['reason'],primary_acceptance=False)
        del raw,prior
        cancelled_path=root/'docs/RUST-NFS-BUFFERED-LIVE-LOSS-CANCELLED-EVIDENCE.json'
        cancelled=read(cancelled_path);raw=zlib.decompress(base64.b64decode(cancelled['report_zlib_base64']))
        assert sha(raw)==cancelled['report_sha256'] and cancelled['qualification_status']=='FAILED'
        stopped=json.loads(raw)
        assert stopped['status']=='FAILED' and not stopped['cleanup_errors'] and not stopped['rust_executed']
        assert not stopped.get('authorization',{}).get('cases',[]) and len(stopped['sources'])==26
        assert 'mkdir /tmp/mount-auth' in stopped['error'] and 'File exists' in stopped['error']
        for item in stopped['sources'].values():assert sha(base64.b64decode(item['base64']))==item['sha256']
        inputs['cancelled_duplicate']=dict(run_id=stopped['run_id'],status='FAILED',
            retained_file=cancelled_path.name,report_sha256=cancelled['report_sha256'],
            reason=cancelled['reason'],rust_executed=False,primary_acceptance=False)
        del raw,stopped
    if args.unstable and not args.live_loss:
        initial_path=root/'docs/RUST-NFS-BUFFERED-UNSTABLE-INITIAL-EVIDENCE.json'
        initial=read(initial_path);raw=zlib.decompress(base64.b64decode(initial['report_zlib_base64']))
        assert sha(raw)==initial['report_sha256'] and initial['qualification_status']=='FAILED'
        failed=json.loads(raw)
        assert failed['status']=='FAILED' and not failed['cleanup_errors'] and not failed['authorization']['cases']
        assert failed['run_id']!=live['run_id'] and len(failed['sources'])==26
        assert 'validate_unstable_resend' in failed['traceback']
        for item in failed['sources'].values():assert sha(base64.b64decode(item['base64']))==item['sha256']
        inputs['initial_attempt']=dict(run_id=failed['run_id'],status='FAILED',retained_file=initial_path.name,
            report_sha256=initial['report_sha256'],reason=initial['reason'])
        del raw,failed
    data=Path(__file__).read_bytes()
    inputs['verifier']=dict(sha256=sha(data),base64=base64.b64encode(data).decode())
    # Keep the exact report bytes and avoid another full in-memory JSON copy.
    compressor=zlib.compressobj(9);hasher=hashlib.sha256();chunks=[]
    with (args.live/'report.json').open('rb') as source:
        while block:=source.read(1048576):
            hasher.update(block);chunks.append(compressor.compress(block))
    chunks.append(compressor.flush());packed=b''.join(chunks)
    save(prefix+'-EVIDENCE.json',dict(format='zlib-base64-json',report_sha256=hasher.hexdigest(),report_zlib_base64=base64.b64encode(packed).decode()))
    save(prefix+'-INPUT-EVIDENCE.json',inputs)
    save('RUST-SLES-EVIDENCE.json',gates['production'])
    save('RUST-SLES-QUALIFICATION-EVIDENCE.json',gates['qualification'])
    print(json.dumps(dict(run_id=live['run_id'],native_probes=6,service_cases=case_count,verified_elf_count=count,driver_snapshots=len(live['sources']),cleanup_errors=[])))


if __name__=='__main__':main()
