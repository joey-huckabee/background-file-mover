#!/usr/bin/env python3
"""Independently verify and retain buffered worker I/O/RPC attribution and fresh SLES evidence."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import tarfile
import zlib
from nfs_rpc import call as decode_call, reply as decode_reply
from nfs_mount_profile import covering, parse
from nfs_io_analysis import analyze


def qualify_objects(trace, analysis):
    """Independent second step: witnessed mount fsid + descriptor inode.

    An operation need not send its first GETATTR during the same syscall that
    flushes its data. Use prior successful open/stat witnesses for the mount,
    preserve full fsid+fileid scope, and never promote bare timing to identity.
    """
    mounts={}
    for match in analysis['metadata_matches']:
        mounts.setdefault(match['mount_id'],set()).add(tuple(match['fsid']))
    assert all(len(values)==1 for values in mounts.values()),'conflicting mount-fsid witnesses'
    witnesses={key:list(next(iter(values))) for key,values in mounts.items()}
    results=[]
    for request in analysis['rpc_operations']:
        ident=analysis['filehandle_identities'].get(request['filehandle_sha256'])
        matched=[];buffers=[]
        if ident:
            for index in request['overlapping_events']:
                event=trace['events'][index]
                for key in ('descriptor','returned_descriptor'):
                    fd=event.get(key)
                    if (fd and fd['filesystem'] in ('nfs','nfs4') and fd['inode']==ident['identity']['fileid']
                            and witnesses.get(fd['mount_id'])==ident['identity']['fsid']):
                        matched.append(dict(event_index=index,descriptor_kind=key,path=fd['path'],
                            mount_id=fd['mount_id'],inode=fd['inode'],syscall=event['name'],result=event['result']))
            if request['operation']['op']==38:
                op=request['operation']
                for index,event in enumerate(trace['events']):
                    fd=event.get('descriptor')
                    if (event.get('syscall') not in (1,18) or not fd or 'payload' not in event or event['result']<=0
                            or fd['filesystem'] not in ('nfs','nfs4') or fd['inode']!=ident['identity']['fileid']
                            or witnesses.get(fd['mount_id'])!=ident['identity']['fsid'] or event['enter_ns']>request['monotonic_ns']):continue
                    position=event['args'][3] if event['syscall']==18 else fd['position']
                    start=op['offset']-position
                    if start<0 or start+op['count']>event['result']:continue
                    payload=zlib.decompress(base64.b64decode(event['payload']['zlib_base64']))
                    if hashlib.sha256(payload[start:start+op['count']]).hexdigest()!=op['data_sha256']:continue
                    buffers.append(dict(event_index=index,path=fd['path'],offset=op['offset'],count=op['count'],
                        relation='write_completed_before_rpc' if event['exit_ns']<request['monotonic_ns'] else 'rpc_during_write'))
        results.append(dict(request_sha256=request['request_sha256'],operation=request['operation']['op'],
            filehandle_sha256=request['filehandle_sha256'],identity=ident['identity'] if ident else None,
            qualified_overlaps=matched,buffer_matches=buffers,plain_overlap_count=len(request['overlapping_events'])))
    return dict(mount_fsid_witnesses=witnesses,operations=results)


def qualification_controls():
    """Same-inode objects on different exports must never match by inode alone."""
    import copy
    trace=dict(events=[dict(name='fchmod',result=0,descriptor=dict(filesystem='nfs4',mount_id='9',inode=12,path='/stage'))])
    analysis=dict(metadata_matches=[dict(mount_id='9',fsid=[68,0])],filehandle_identities={'fh':dict(identity=dict(fsid=[68,0],fileid=12))},
        rpc_operations=[dict(request_sha256='r',operation=dict(op=5),filehandle_sha256='fh',overlapping_events=[0])])
    def count(value):return len(qualify_objects(trace,value)['operations'][0]['qualified_overlaps'])
    assert count(analysis)==1
    cases=[]
    for mode in ('foreign_fsid','foreign_inode','unwitnessed_mount','no_overlap','unknown_handle'):
        value=copy.deepcopy(analysis)
        if mode=='foreign_fsid':value['filehandle_identities']['fh']['identity']['fsid']=[69,0]
        elif mode=='foreign_inode':value['filehandle_identities']['fh']['identity']['fileid']=13
        elif mode=='unwitnessed_mount':value['metadata_matches']=[]
        elif mode=='no_overlap':value['rpc_operations'][0]['overlapping_events']=[]
        else:value['filehandle_identities']={}
        assert count(value)==0
        cases.append(dict(control=mode,passed=True))
    value=copy.deepcopy(analysis);value['metadata_matches'].append(dict(mount_id='9',fsid=[69,0]))
    try:qualify_objects(trace,value)
    except AssertionError:cases.append(dict(control='conflicting_mount_witnesses',passed=True))
    else:raise AssertionError('conflicting mount witnesses accepted')
    data=b'abc'
    buffer_trace=dict(events=[dict(syscall=1,args=[7,1000,3,0,0,0],name='write',enter_ns=100,exit_ns=120,result=3,
        descriptor=dict(filesystem='nfs4',mount_id='9',inode=12,path='/stage',position=1024),
        payload=dict(zlib_base64=base64.b64encode(zlib.compress(data)).decode()))])
    value=copy.deepcopy(analysis)
    value['rpc_operations'][0].update(monotonic_ns=150,overlapping_events=[],
        operation=dict(op=38,offset=1024,count=3,data_sha256=hashlib.sha256(data).hexdigest()))
    assert len(qualify_objects(buffer_trace,value)['operations'][0]['buffer_matches'])==1
    for mode in ('foreign_bytes','wrong_range','failed_write','after_request'):
        sample=copy.deepcopy(buffer_trace);event=sample['events'][0]
        if mode=='foreign_bytes':event['payload']['zlib_base64']=base64.b64encode(zlib.compress(b'xyz')).decode()
        elif mode=='wrong_range':event['descriptor']['position']=1025
        elif mode=='failed_write':event['result']=-5
        else:event.update(enter_ns=160,exit_ns=180)
        assert not qualify_objects(sample,value)['operations'][0]['buffer_matches']
        cases.append(dict(control='buffer_'+mode,passed=True))
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('live', type=Path)
    parser.add_argument('--production-gate', required=True, type=Path)
    parser.add_argument('--qualification-gate', required=True, type=Path)
    args = parser.parse_args()
    points = ('claim_apply', 'copy_chunk')
    expected_cases = 8
    prefix = 'RUST-NFS-BUFFERED-IO'
    root = Path(__file__).resolve().parents[1]

    def read(path):
        return json.loads(path.read_text(encoding='utf-8'))

    def sha(data):
        return hashlib.sha256(data).hexdigest()

    def save(name, value):
        (root/'docs'/name).write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8', newline='\n')

    current = {p.relative_to(root/'rust').as_posix(): p.read_bytes()
               for child in (root/'rust').iterdir() if child.name not in ('target', 'validation')
               for p in (child.rglob('*') if child.is_dir() else [child]) if p.is_file()}
    live = read(args.live/'report.json')
    assert live['status'] == 'PASSED' and not live['cleanup_errors'] and live['rust_executed']
    assert live['glibc'] == 'glibc 2.22' and live['config'] == read(root/'scripts/rust-platform.json')
    assert not live['production_nfs_enabled'] and not live['source_deletion_enabled']
    assert live['observer_capabilities'] == ['SYS_PTRACE', 'DAC_READ_SEARCH']
    client = dict(line.split(':', 1) for line in live['client_security'].splitlines() if ':' in line)
    assert all(int(client[k], 16) == ((1 << 21) | (1 << 19) | (1 << 2)) for k in ('CapPrm', 'CapEff', 'CapBnd'))
    assert int(client['CapInh'], 16) == int(client['CapAmb'], 16) == 0 and client['NoNewPrivs'].strip() == '1'
    assert len(live['sources']) == 24
    assert len(live['checks']) == 43 and all(c['passed'] for c in live['checks'])
    assert live['authorization']['passed']
    for name, item in live['sources'].items():
        data = base64.b64decode(item['base64'])
        assert sha(data) == item['sha256'] and data == (root/'scripts'/name).read_bytes()
    cases = live['authorization']['cases']
    assert len(cases) == expected_cases and {(c['layout'], c['profile'], c['point']) for c in cases} == {
        (layout, profile, point) for layout in ('same-share', 'separate-shares')
        for profile in ('debug', 'release')
        for point in points}
    assert live['authorization']['matrix'] == 'buffered-io'
    expected_hash = sha(bytes(2*1048576)+b'0123456789abcdefg')
    def wire_check(wire):
        assert not wire['trace_overflow'] and not wire['errors']
        assert len(wire['trace']) <= 8192 and wire['trace_bytes'] <= 64*1048576
        total = 0
        for row in wire['trace']:
            data = zlib.decompress(base64.b64decode(row['payload_zlib_base64']))
            assert sha(data) == row['sha256']
            total += len(data)
            try:
                decoded = (decode_call if row['direction'] == 'call' else decode_reply)(data)
            except ValueError:
                decoded = None
            assert decoded == row['decoded']
        assert total == wire['trace_bytes']

    summaries = []
    clients = None
    observer_ids = set()
    for c in cases:
        assert c['passed'] and c['source_and_state_preserved'] and c['source_retained']
        assert c['scenario_id'] == 'SC-111' and c['producer_reuse_after_202'] and not c['service_sync_loss_tested']
        assert c['original_source'][1].split()[0] == expected_hash
        assert c['source_identity_after'] == c['original_source'][0]
        assert c['database_after'] == c['database_before'] and c['enrollment_after'] == c['enrollment_before']
        assert c['binary_sha256'] == live['authorization']['gates']['qualification']['artifacts'][c['profile']]['sha256']
        assert all(c['config'][role+'_binding']['nfs_mount']['profile'] == 'NMP-41B' for role in ('source','destination'))
        assert (c['devices'][0] == c['devices'][1]) == (c['layout'] == 'same-share') and c['devices'][2] not in c['devices'][:2]
        mounts = [covering(parse(c['inventory']),c['config'][role+'_root']) for role in ('source','destination')]
        assert (mounts[0] == mounts[1]) == (c['layout'] == 'same-share')
        assert all('noac' not in m['super'] and 'sync' not in m['super'] for m in mounts)
        security = dict(line.split(':',1) for line in c['worker_security'].splitlines() if ':' in line)
        assert security['Uid'].split() == security['Gid'].split() == ['1000']*4 and security['NoNewPrivs'].strip() == '1'
        assert all(int(security[k],16) == 0 for k in ('CapInh','CapPrm','CapEff'))
        rows = c['clock_namespaces']
        assert len(rows) == (3 if c['layout']=='same-share' else 4) and len(set(rows.values())) == 1
        assert all(v.startswith('time:[') for v in rows.values())
        relay_ids = {live['authorization']['relays'][r]['container'] for r in c['wire']}
        assert relay_ids <= set(rows)
        remaining = set(rows)-relay_ids
        clients = remaining if clients is None else clients & remaining
        observer_ids |= remaining
        trace = c['trace']
        assert trace['events'] and len(trace['events'])<=8192 and trace['payload_bytes']<=8*1048576
        assert trace['event_limit']==8192 and trace['payload_limit']==8*1048576
        total_payload=0
        for event in trace['events']:
            assert event['enter_ns']<=event['exit_ns'] and len(event['args'])==6
            if 'payload' in event:
                payload=event['payload'];raw=zlib.decompress(base64.b64decode(payload['zlib_base64']))
                assert sha(raw)==payload['sha256'] and len(raw)==payload['size']==event['args'][2]
                assert event['syscall'] in (1,18) and event['descriptor']['filesystem'] in ('nfs','nfs4')
                total_payload+=len(raw)
        assert total_payload==trace['payload_bytes']
        assert c['io_analysis']==analyze(trace,c['wire'])
        assert trace['passed'] and not trace.get('cleanup_error') and c['worker_exit'] in ('Z','gone')
        expected_exit = 'zero' if c['point']=='claim_apply' else 'supervised-delivery'
        assert trace['expected_exit'] == expected_exit and trace['exit_status'] in ((0,) if expected_exit=='zero' else (0,9))
        if c['point']=='copy_chunk':
            assert c['retirement_committed_receipt']['state']=='Committed' and c['retirement_committed_receipt']['details']['files'][0]['attempt']==1
        for wire in c['wire'].values(): wire_check(wire)
        assert sum(len(w['trace']) for w in c['wire'].values()) > 0
        calls = [dict(r,relay_role=role) for role,w in c['wire'].items() for r in w['trace'] if r['direction']=='call']
        replies, pairs = [], []
        for role, wire in c['wire'].items():
            pending = {}
            for row in wire['trace']:
                key = row['connection'], row['xid']
                if row['direction']=='call':
                    pending[key] = row
                else:
                    replies.append(row)
                    if key in pending:
                        request = pending.pop(key)
                        assert request['monotonic_ns'] <= row['monotonic_ns']
                        pairs.append((request,row))
        all_syncs = [r for r in trace['syncs'] if int(r['mount_id']) in {m['id'] for m in mounts}]
        assert all_syncs
        for sync in trace['syncs']:
            assert sync['syscall'] in (74,75) and sync['result']==0 and sync['enter_ns'] <= sync['exit_ns']
            assert sync['rpc_calls'] == [r for r in calls if sync['enter_ns'] <= r['monotonic_ns'] <= sync['exit_ns']]
        # Authoritative totals include mount-root syncs, not just descendant paths
        # in the helper's primary-role convenience selection.
        ops = sorted({op['op'] for sync in all_syncs for call in sync['rpc_calls'] if call['decoded'] for op in call['decoded']['operations'] if op['op'] in (5,38)})
        unknown = sum(call['decoded'] is None for sync in all_syncs for call in sync['rpc_calls'])
        summaries.append(dict(layout=c['layout'],profile=c['profile'],point=c['point'],nfs_sync_count=len(all_syncs),
            rpc_calls_inside_sync=sum(len(x['rpc_calls']) for x in all_syncs),undecoded_calls_inside_sync=unknown,observed_operations=ops,
            full_window_rpc_calls=len(calls),full_window_undecoded_calls=sum(r['decoded'] is None for r in calls),
            rpc_replies_inside_sync=sum(s['enter_ns']<=r['monotonic_ns']<=s['exit_ns'] for s in all_syncs for r in replies),
            captured_rpc_pairs_spanning_sync_entry=sum(a['monotonic_ns']<s['enter_ns']<b['monotonic_ns'] for s in all_syncs for a,b in pairs),
            full_window_operations={str(op):sum(o['op']==op for r in calls if r['decoded'] for o in r['decoded']['operations']) for op in (5,38)}))
        summaries[-1]['io_event_count']=len(trace['events'])
        summaries[-1]['write_payload_bytes']=trace['payload_bytes']
        summaries[-1]['metadata_anchor_count']=len(c['io_analysis']['metadata_matches'])
        summaries[-1]['write_anchor_count']=len(c['io_analysis']['write_matches'])
        summaries[-1]['anchored_operation_counts']={str(op):sum(bool(r['anchored_descriptor_events']) and r['operation']['op']==op for r in c['io_analysis']['rpc_operations']) for op in (5,38)}
        summaries[-1]['operation_syscalls']={str(op):sorted({trace['events'][n]['name'] for r in c['io_analysis']['rpc_operations'] if r['operation']['op']==op for n in r['anchored_descriptor_events']}) for op in (5,38)}
        summaries[-1]['qualified_object_analysis']=qualify_objects(trace,c['io_analysis'])
        summaries[-1]['rpc_results']=[dict(request_sha256=a['sha256'],reply_sha256=b['sha256'],
            request_ns=a['monotonic_ns'],reply_ns=b['monotonic_ns'],rpc_status=b['decoded']['status'] if b['decoded'] else None,
            operation_results=[op for op in b['decoded']['operations'] if op['op'] in (5,38)] if b['decoded'] else None)
            for a,b in pairs if a['decoded'] and any(op['op'] in (5,38) for op in a['decoded']['operations'])]
        primary_ops = sorted({op['op'] for sync in c['nfs_syncs'] for call in sync['rpc_calls'] if call['decoded'] for op in call['decoded']['operations'] if op['op'] in (5,38)})
        assert primary_ops == c['observed_sync_operations'] and set(primary_ops) <= set(ops)
        assert c['full_nfs_sync_operations'] == ops
        initial = c['initial_response']
        assert (initial[0]==202 and initial[1]['source_paths_released']) or (initial[0]==503 and initial[1]['retryable'] and not initial[1]['source_paths_released'])
        assert c['confirmed_response'][0]==202 and c['confirmed_response'][1]['job_id']=='1' and c['confirmed_response'][1]['source_paths_released']
        assert c['committed']['state']=='Committed' and c['committed']['details']['files'][0]['attempt']==1
        assert not c['committed']['details']['source_cleanup_enabled'] and c['manifest']['files'][0]['sha256']==expected_hash
    assert clients and len(clients)==1 and len(observer_ids-clients)==8
    assert not live['authorization']['capabilities']
    assert live['authorization']['io_analysis_tests']['passed']
    for relay in live['authorization']['relays'].values():
        sec=dict(line.split(':',1) for line in relay['security'].splitlines() if ':' in line)
        assert sec['Uid'].split()==['1000']*4 and sec['NoNewPrivs'].strip()=='1'
        assert all(int(sec[k],16)==0 for k in ('CapInh','CapPrm','CapEff')) and not relay['final_state']['errors']
    inputs=dict(live_run_id=live['run_id'],matrix='buffered-io',rust_input_count=len(current),
        rust_inputs={name:sha(data) for name,data in current.items()},gates={},case_analysis=summaries)
    inputs['object_qualification_negative_controls']=qualification_controls()
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
    initial_path = root/'docs/RUST-NFS-BUFFERED-IO-INITIAL-EVIDENCE.json'
    initial = read(initial_path)
    raw = zlib.decompress(base64.b64decode(initial['report_zlib_base64']))
    assert sha(raw)==initial['report_sha256'] and initial['qualification_status']=='FAILED'
    failed=json.loads(raw)
    assert failed['status']=='FAILED' and not failed['cleanup_errors']
    assert 'conflicting filehandle identity' in failed['error'] and len(failed['sources'])==24
    inputs['initial_attempt']=dict(run_id=failed['run_id'],status='FAILED',retained_file=initial_path.name,
        report_sha256=initial['report_sha256'],reason=initial['reason'])
    data = Path(__file__).read_bytes()
    inputs['verifier'] = dict(sha256=sha(data), base64=base64.b64encode(data).decode())
    # Publish only after every independent assertion passes.
    packed=json.dumps(live,separators=(',',':')).encode()
    save(prefix+'-EVIDENCE.json',dict(format='zlib-base64-json',report_sha256=sha(packed),report_zlib_base64=base64.b64encode(zlib.compress(packed,9)).decode()))
    save(prefix+'-INPUT-EVIDENCE.json', inputs)
    save('RUST-SLES-EVIDENCE.json', gates['production'])
    save('RUST-SLES-QUALIFICATION-EVIDENCE.json', gates['qualification'])
    print(json.dumps(dict(run_id=live['run_id'],live_cases=len(cases),nfs_syncs=sum(r['nfs_sync_count'] for r in summaries),
        observed_operations=sorted({op for r in summaries for op in r['observed_operations']}),
        attributed_operations=sum(bool(op['anchored_descriptor_events']) for c in cases for op in c['io_analysis']['rpc_operations']),verified_elf_count=count,driver_snapshots=len(live['sources']),cleanup_errors=[])))




if __name__ == '__main__':
    main()
