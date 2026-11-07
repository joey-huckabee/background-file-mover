#!/usr/bin/env python3
"""Independently verify and retain buffered-publication and fresh SLES evidence."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import tarfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('live', type=Path)
    parser.add_argument('--production-gate', required=True, type=Path)
    parser.add_argument('--qualification-gate', required=True, type=Path)
    parser.add_argument('--post-unlink', action='store_true', help='Verify the eight after-unlink/before-directory-sync cases and retain their separate evidence')
    args = parser.parse_args()
    points = ('file_unlink_sync', 'manifest_unlink_sync') if args.post_unlink else (
        'file_link_sync', 'file_unlink', 'manifest_link_sync', 'manifest_unlink')
    expected_cases = 8 if args.post_unlink else 16
    prefix = 'RUST-NFS-BUFFERED-POST-UNLINK' if args.post_unlink else 'RUST-NFS-BUFFERED-PUBLICATION'
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
    assert live['observer_capabilities'] == ([] if args.post_unlink else ['SYS_PTRACE', 'DAC_READ_SEARCH'])
    if args.post_unlink:
        client = dict(line.split(':', 1) for line in live['client_security'].splitlines() if ':' in line)
        assert all(int(client[k], 16) == 1 << 21 for k in ('CapPrm', 'CapEff', 'CapBnd'))  # SYS_ADMIN only.
        assert int(client['CapInh'], 16) == int(client['CapAmb'], 16) == 0 and client['NoNewPrivs'].strip() == '1'
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
    if args.post_unlink:
        assert live['authorization']['matrix'] == 'buffered-post-unlink'
    expected_hash = sha(bytes(2*1048576)+b'0123456789abcdefg')
    raw_closed = 0
    for c in cases:
        assert c['passed'] and c['original_state_publications_and_producer_bytes_preserved'] and c['source_retained']
        assert c['original_source'][1].split()[0] == expected_hash
        assert c['binary_sha256'] == live['authorization']['gates']['qualification']['artifacts'][c['profile']]['sha256']
        assert all(c['config'][role+'_binding']['nfs_mount']['profile'] == 'NMP-41B' for role in ('source', 'destination'))
        assert (c['devices'][0] == c['devices'][1]) == (c['layout'] == 'same-share')
        assert c['devices'][2] not in c['devices'][:2]
        security = dict(line.split(':', 1) for line in c['worker_security'].splitlines() if ':' in line)
        assert security['Uid'].split() == security['Gid'].split() == ['1000']*4
        assert security['NoNewPrivs'].strip() == '1'
        assert all(int(security[k], 16) == 0 for k in ('CapInh', 'CapPrm', 'CapEff'))
        assert c['handoff']['source_paths_released'] and c['handoff']['job_id'] == '1'
        assert c['replay_before_outage']['code'] == 202 and c['replay_before_outage']['response']['job_id'] == '1'
        manifest = c['point'].startswith('manifest')
        active = 'COMMITTED.json' if manifest else 'nested/data.bin'
        old = '.staging/COMMITTED.part' if manifest else '.staging/1.part'
        before, after = c['publication_before_outage'], c['publication_after_recovery']
        if args.post_unlink:
            assert before[old] is None and before[active]['links'] == 1
            assert c['outage_health_seconds'] < 5 and c['outage_job_seconds'] < 5
            assert c['staging_absent_before_directory_sync'] and c['staging_absent_after_old_exit']
            assert c['publication_after_old_exit'][old] is None
            assert c['publication_after_old_exit'][active] == before[active]
            assert c['pause_unreleased_before_crash'] and c['worker_stopped_before_crash'] in ('T', 't')
        else:
            assert before[active] == before[old] and before[active]['links'] == 2
        for name in (active, 'nested/data.bin'):
            assert all(before[name][k] == after[name][k] for k in ('device', 'inode', 'size', 'sha256'))
        assert after['.staging/1.part'] is None and after['.staging/COMMITTED.part'] is None
        assert after['nested/data.bin']['links'] == after['COMMITTED.json']['links'] == 1
        if not manifest:
            assert before['COMMITTED.json'] is None and c['publication_after_old_exit']['COMMITTED.json'] is None
        if c['point'].endswith('_unlink'):
            blocked = c['blocked_unlink']
            fields = blocked['syscall'].split()
            assert blocked['state'] == 'D' and blocked['nfsd_threads'] == 0
            assert len(fields) == 9 and fields[0] == '263' and int(fields[3], 16) == 0
            assert blocked['parent'] == c['config']['destination_root']+'/1/.staging'
        else:
            assert c['interruption_kind'] == ('unlink_returned_following_directory_sync_not_called' if args.post_unlink
                                               else 'link_returned_following_sync_not_called')
        assert len(c['orphan_samples']) == 2
        assert all(s['status']['exit_code'] == 2 and s['status']['snapshot']['phase'] == 'OwnerUnavailable'
                   for s in c['orphan_samples'])
        raw_closed += any(not s['guard']['contended'] for s in c['orphan_samples'])
        assert len(c['contenders']) == 3 and all(x['seconds'] < 6 and 'local instance or surviving worker already owns state' in x['diagnostic'] for x in c['contenders'])
        assert c['old_worker_exit'] in ('Z', 'gone') and c['status_after_exit']['snapshot']['phase'] == 'NoActiveOwner'
        assert all(t['state'] in ('Z', 'X', 'x') for t in c['old_threads_before_recovery'])
        assert c['committed']['state'] == 'Committed' and c['committed']['details']['files'][0]['attempt'] == 1
        assert not c['committed']['details']['source_cleanup_enabled']
        assert c['replay']['job_id'] == '1' and c['replay']['source_paths_released']
        assert c['manifest']['files'][0]['sha256'] == expected_hash
    inputs = dict(live_run_id=live['run_id'], matrix='buffered-post-unlink' if args.post_unlink else 'buffered-publication',
                  rust_input_count=len(current),
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
    if not args.post_unlink:
        initial_path = root/'docs/RUST-NFS-BUFFERED-PUBLICATION-INITIAL-EVIDENCE.json'
        initial = read(initial_path)
        assert initial['status'] == 'FAILED' and not initial['cleanup_errors']
        assert len(initial['authorization']['cases']) == 1 and 'assert code == 202' in initial['traceback']
        for item in initial['sources'].values():
            assert sha(base64.b64decode(item['base64'])) == item['sha256']
        inputs['initial_evidence'] = dict(path=initial_path.name, sha256=sha(initial_path.read_bytes()), status=initial['status'])
    else:
        initial_path = root/'docs/RUST-NFS-BUFFERED-POST-UNLINK-INITIAL-EVIDENCE.json'
        initial = read(initial_path)
        assert initial['status'] == 'FAILED' and not initial['cleanup_errors']
        assert len(initial['authorization']['cases']) == 2
        assert initial['authorization']['cases'][0]['passed'] and not initial['authorization']['cases'][1]['passed']
        assert initial['authorization']['cases'][1]['outage_api_seconds'] >= 5 and 'outage_api_seconds' in initial['traceback']
        for item in initial['sources'].values():
            assert sha(base64.b64decode(item['base64'])) == item['sha256']
        inputs['initial_evidence'] = dict(path=initial_path.name, sha256=sha(initial_path.read_bytes()), status=initial['status'])
    data = Path(__file__).read_bytes()
    inputs['verifier'] = dict(sha256=sha(data), base64=base64.b64encode(data).decode())
    # Publish only after every independent assertion passes.
    save(prefix+'-EVIDENCE.json', live)
    save(prefix+'-INPUT-EVIDENCE.json', inputs)
    save('RUST-SLES-EVIDENCE.json', gates['production'])
    save('RUST-SLES-QUALIFICATION-EVIDENCE.json', gates['qualification'])
    print(json.dumps(dict(run_id=live['run_id'], live_cases=len(cases), blocked_unlinks=0 if args.post_unlink else 8,
        pre_sync_crashes=8, verified_elf_count=count, rust_inputs=len(current),
        driver_snapshots=len(live['sources']), raw_guard_closed_cases=raw_closed, cleanup_errors=[])))


if __name__ == '__main__':
    main()
