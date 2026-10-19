#!/usr/bin/env python3
"""Independently verify and retain buffered pre-202 source-claim and fresh SLES evidence."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import tarfile
from nfs_mount_profile import covering, parse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('live', type=Path)
    parser.add_argument('--production-gate', required=True, type=Path)
    parser.add_argument('--qualification-gate', required=True, type=Path)
    args = parser.parse_args()
    points = ('claim_link_rpc', 'claim_unlink_rpc')
    expected_cases = 8
    prefix = 'RUST-NFS-BUFFERED-CLAIM'
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
    assert len(live['sources']) == 10
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
    assert live['authorization']['matrix'] == 'buffered-claims'
    expected_hash = sha(bytes(2*1048576)+b'0123456789abcdefg')
    raw_closed = 0
    for c in cases:
        assert c['passed'] and c['original_state_claim_inode_and_producer_bytes_preserved'] and c['source_retained']
        assert c['scenario_id'] == 'SC-109' and c['producer_reuse_after_202'] and c['second_job_absent']
        assert c['original_source'][1].split()[0] == expected_hash
        assert c['binary_sha256'] == live['authorization']['gates']['qualification']['artifacts'][c['profile']]['sha256']
        assert all(c['config'][role+'_binding']['nfs_mount']['profile'] == 'NMP-41B' for role in ('source', 'destination'))
        assert (c['devices'][0] == c['devices'][1]) == (c['layout'] == 'same-share')
        assert c['devices'][2] not in c['devices'][:2]
        mounts = [covering(parse(c['inventory']), c['config'][role+'_root']) for role in ('source', 'destination')]
        assert (mounts[0] == mounts[1]) == (c['layout'] == 'same-share')
        assert all('noac' not in m['super'] for m in mounts)
        security = dict(line.split(':', 1) for line in c['worker_security'].splitlines() if ':' in line)
        assert security['Uid'].split() == security['Gid'].split() == ['1000']*4
        assert security['NoNewPrivs'].strip() == '1'
        assert all(int(security[k], 16) == 0 for k in ('CapInh', 'CapPrm', 'CapEff'))
        job = c['job_before_outage']
        assert job['state'] == 'Accepted' and not job['source_paths_released'] and not job['details']['source_cleanup_enabled']
        response = c['initial_submission']['response']
        assert response[0] == 503 and response[1]['retryable'] and not response[1]['source_paths_released']
        assert response[1]['error'] in ('handoff_pending', 'service_busy')
        assert c['status_during_outage']['snapshot']['phase'] == 'Running' and c['status_during_outage']['exit_code'] == 0
        assert c['outage_health_seconds'] < 5 and c['outage_job_seconds'] < 5
        before = c['source_before_outage']
        original = before['producer']
        assert original['sha256'] == expected_hash and original['size'] == 2*1048576+17
        linking = c['point'] == 'claim_link_rpc'
        if linking:
            assert before['custody'] is None and original['links'] == 1
        else:
            assert before['custody'] == original and original['links'] == 2
        blocked = c['blocked_claim_syscall']
        fields = blocked['syscall'].split()
        assert blocked['state'] == 'D' and blocked['nfsd_threads'] == 0
        assert len(fields) == 9 and fields[0] == ('265' if linking else '263')
        assert blocked['old_parent'] == c['config']['source_root']+'/current/nested'
        if linking:
            assert blocked['new_parent'] == c['config']['source_root']+'/.file-mover/1-0' and int(fields[5], 16) == 0
        else:
            assert int(fields[3], 16) == 0
        aliases = [x for x in c['source_after_old_exit'].values() if x is not None]
        assert aliases
        for obj in aliases:
            assert all(obj[k] == original[k] for k in ('device', 'inode', 'size', 'sha256')) and obj['links'] == len(aliases)
        custody = c['source_after_recovery']['custody']
        assert all(custody[k] == original[k] for k in ('device', 'inode', 'size', 'sha256')) and custody['links'] == 1
        assert c['confirmed_custody_replay'][0] == 202 and c['confirmed_custody_replay'][1]['job_id'] == '1'
        assert c['confirmed_custody_replay'][1]['source_paths_released']
        assert len(c['orphan_samples']) == 2
        assert all(x['status']['exit_code'] == 2 and x['status']['snapshot']['phase'] == 'OwnerUnavailable' for x in c['orphan_samples'])
        raw_closed += any(not x['guard']['contended'] for x in c['orphan_samples'])
        assert len(c['contenders']) == 3 and all(x['seconds'] < 6 and 'local instance or surviving worker already owns state' in x['diagnostic'] for x in c['contenders'])
        assert c['old_worker_exit'] in ('Z', 'gone') and c['status_after_exit']['snapshot']['phase'] == 'NoActiveOwner'
        assert all(t['state'] in ('Z', 'X', 'x') for t in c['old_threads_before_recovery'])
        assert c['committed']['state'] == 'Committed' and c['committed']['details']['files'][0]['attempt'] == 1
        assert not c['committed']['details']['source_cleanup_enabled']
        assert c['replay']['job_id'] == '1' and c['replay']['source_paths_released']
        assert c['manifest']['files'][0]['sha256'] == expected_hash
        after = c['publication_after_recovery']
        assert after['.staging/1.part'] is None and after['.staging/COMMITTED.part'] is None
        assert after['nested/data.bin']['sha256'] == expected_hash
        assert after['nested/data.bin']['links'] == after['COMMITTED.json']['links'] == 1
    inputs = dict(live_run_id=live['run_id'], matrix='buffered-claims', rust_input_count=len(current),
                  rust_inputs={name: sha(data) for name, data in current.items()}, gates={})
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
                  all_driver_snapshots_match_current=True, observed_raw_guard_closed_cases=raw_closed)
    data = Path(__file__).read_bytes()
    inputs['verifier'] = dict(sha256=sha(data), base64=base64.b64encode(data).decode())
    # Publish only after every independent assertion passes.
    save(prefix+'-EVIDENCE.json', live)
    save(prefix+'-INPUT-EVIDENCE.json', inputs)
    save('RUST-SLES-EVIDENCE.json', gates['production'])
    save('RUST-SLES-QUALIFICATION-EVIDENCE.json', gates['qualification'])
    print(json.dumps(dict(run_id=live['run_id'], live_cases=len(cases), blocked_links=4, blocked_unlinks=4,
        verified_elf_count=count, rust_inputs=len(current), driver_snapshots=len(live['sources']),
        raw_guard_closed_cases=raw_closed, cleanup_errors=[])))



if __name__ == '__main__':
    main()
