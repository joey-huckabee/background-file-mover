#!/usr/bin/env python3
"""Independently verify and retain buffered synchronization/RPC observations and fresh SLES evidence."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import tarfile
import zlib
from nfs_rpc import call as decode_call, reply as decode_reply
from nfs_sync_capability import validate_resend
from nfs_mount_profile import covering, parse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('live', type=Path)
    parser.add_argument('--production-gate', required=True, type=Path)
    parser.add_argument('--qualification-gate', required=True, type=Path)
    args = parser.parse_args()
    points = ('claim_apply', 'copy_chunk')
    expected_cases = 8
    prefix = 'RUST-NFS-BUFFERED-SYNC'
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
    # Increment 77 adds opt-in I/O drivers; synchronization-only behavior stays
    # available with either historical or expanded exact source inventories.
    assert len(live['sources']) in (21,24)
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
    assert live['authorization']['matrix'] == 'buffered-sync'
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
        primary_ops = sorted({op['op'] for sync in c['nfs_syncs'] for call in sync['rpc_calls'] if call['decoded'] for op in call['decoded']['operations'] if op['op'] in (5,38)})
        assert primary_ops == c['observed_sync_operations'] and set(primary_ops) <= set(ops)
        assert c['full_nfs_sync_operations'] == ops
        initial = c['initial_response']
        assert (initial[0]==202 and initial[1]['source_paths_released']) or (initial[0]==503 and initial[1]['retryable'] and not initial[1]['source_paths_released'])
        assert c['confirmed_response'][0]==202 and c['confirmed_response'][1]['job_id']=='1' and c['confirmed_response'][1]['source_paths_released']
        assert c['committed']['state']=='Committed' and c['committed']['details']['files'][0]['attempt']==1
        assert not c['committed']['details']['source_cleanup_enabled'] and c['manifest']['files'][0]['sha256']==expected_hash
    assert clients and len(clients)==1 and len(observer_ids-clients)==8
    cap = live['authorization']['capabilities']
    assert len(cap)==2 and {r['layout'] for r in cap}=={'same-share','separate-shares'}
    for item in cap:
        assert item['passed'] and len(item['observations'])==1
        discovery = item['observations'][0]
        assert discovery['passed'] and discovery['trace']['passed'] and discovery['trace']['exit_status']==0
        assert set(discovery['wires']) == ({'source'} if item['layout']=='same-share' else {'source','destination'})
        for wire in discovery['wires'].values(): wire_check(wire)
        assert discovery['wire']['trace'] == [dict(r,relay_role=role) for role,w in discovery['wires'].items() for r in w['trace']]
        assert len(set(discovery['clock_namespaces'].values()))==1 and set(clients) <= set(discovery['clock_namespaces'])
        assert len(discovery['clock_namespaces']) == (3 if item['layout']=='same-share' else 4)
        wire_check(discovery['wire'])
        assert item['service_observed_operations'] == sorted({op for r in summaries if r['layout']==item['layout'] for op in r['observed_operations']})
        assert set(item['available_operations']) == set(item['service_observed_operations']) & set(discovery['observed_sync_operations'])
        if not item['available_operations']:
            assert not item['withholding_available'] and not item['withholding'] and item['limitation']
            continue
        assert item['withholding_available'] and {r['label'] for r in item['withholding']}=={'release','drop'}
        for row in item['withholding']:
            assert row['passed'] and row['operation'] in item['available_operations']
            raw=row['native_syscall'].split()
            assert raw[0]=='74' and int(raw[1],16)==row['fd'] and row['pending_fd_path']==row['target']
            assert row['server_threads']=='2' and row['server_sha256_while_withheld']==sha(b'S'*4096)
            assert row['server_identity_after']==row['server_identity_while_withheld'] and row['server_sha256_after']==row['server_sha256_while_withheld']
            assert row['held']['held'] and not row['held']['forwarded']
            for held in row['held']['held']:
                assert held['xid']==held['request']['decoded']['xid']==held['reply']['xid'] and held['reply']['status']==0
                assert any(op['op']==row['operation'] and op['status']==0 for op in held['reply']['operations'])
                if row['operation']==38:
                    arg=next(op for op in held['request']['decoded']['operations'] if op['op']==38)
                    ret=next(op for op in held['reply']['operations'] if op['op']==38)
                    assert arg['offset']==0 and arg['count']==4096 and arg['data_sha256']==sha(b'S'*4096)
                    assert arg['stable']==2 and ret['count']==4096 and ret['committed']==2
            wire_check(row['wire'])
            assert 'fsync returned 0' in row['probe_output']
            if row['label']=='drop': assert validate_resend(row,row['operation'])==row['resend_validation']
            else: assert row['settled']['released'] and not row['settled']['dropped']
    for relay in live['authorization']['relays'].values():
        sec=dict(line.split(':',1) for line in relay['security'].splitlines() if ':' in line)
        assert sec['Uid'].split()==['1000']*4 and sec['NoNewPrivs'].strip()=='1'
        assert all(int(sec[k],16)==0 for k in ('CapInh','CapPrm','CapEff')) and not relay['final_state']['errors']
    probe=live['authorization']['probe'];binary=(args.live/'nfs-sync-probe').read_bytes()
    assert sha(binary)==probe['sha256'] and binary.startswith(b'\x7fELF') and probe['source_sha256']==sha((root/'scripts/nfs_sync_probe.c').read_bytes())
    assert probe['elf']['interpreter']==live['config']['interpreter']
    inputs=dict(live_run_id=live['run_id'],matrix='buffered-sync',rust_input_count=len(current),
        rust_inputs={name:sha(data) for name,data in current.items()},gates={},case_analysis=summaries,
        fixture_probe=dict(**probe,binary_base64=base64.b64encode(binary).decode()))
    # build_probe imports the unchanged gate's ELF auditor dynamically. Retain
    # its exact source as well as the 21 drivers captured by the live runner.
    auditor = (root/'scripts/check-rust-sles.py').read_bytes()
    inputs['probe_auditor'] = dict(path='scripts/check-rust-sles.py',sha256=sha(auditor),
                                 base64=base64.b64encode(auditor).decode())
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
    initial_path = root/'docs/RUST-NFS-BUFFERED-SYNC-INITIAL-EVIDENCE.json'
    initial = read(initial_path)
    initial_raw = zlib.decompress(base64.b64decode(initial['report_zlib_base64']))
    assert sha(initial_raw) == initial['report_sha256'] and initial['qualification_status']=='REJECTED_SCOPE'
    rejected = json.loads(initial_raw)
    assert rejected['status']=='PASSED' and not rejected['cleanup_errors']
    assert len(rejected['authorization']['cases'])==8 and len(rejected['sources'])==21
    assert rejected['run_id'] != live['run_id']
    inputs['initial_attempt'] = dict(run_id=rejected['run_id'],qualification_status=initial['qualification_status'],
        retained_file=initial_path.name,report_sha256=initial['report_sha256'],reason=initial['reason'])
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
        native_withholding_controls=sum(len(r['withholding']) for r in cap),verified_elf_count=count,driver_snapshots=len(live['sources']),cleanup_errors=[])))




if __name__ == '__main__':
    main()
