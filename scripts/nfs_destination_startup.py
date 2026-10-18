"""Destination-only outage before startup; source/control remain available."""
import json
import time
import traceback
from nfs_bootstrap_state import (
    prepare, local_evidence, source_evidence, receipt_evidence,
    destination_evidence, partial_evidence, recovered_both,
)


def qualify(Case, run, execute, spawn, restore, output, client, results, endpoints):
    def status(c, phase=None):
        began = time.monotonic()
        reply = execute(f'LD_BIND_NOW=1 {c.binary} --status {c.config_path}', '1000:1000', check=False)
        value = json.loads(reply.stdout)
        row = dict(exit_code=reply.returncode, seconds=round(time.monotonic() - began, 3), snapshot=value)
        assert row['seconds'] < 5 and reply.returncode in (0, 2), row
        if phase:
            assert value['phase'] == phase, row
        return row

    def epoch(c):
        return json.loads(execute(f'cat {c.base}/state/workers.json', '1000:1000').stdout)

    def tasks(main, worker):
        script = f'for file in /proc/{main}/task/*/stat /proc/{worker}/task/*/stat; do test ! -r "$file" || cat "$file" 2>/dev/null || true; done'
        rows = []
        for line in execute(script, '1000:1000').stdout.splitlines():
            head, rest = line.rsplit(') ', 1)
            fields = rest.split()
            rows.append(dict(tid=int(head.split()[0]), state=fields[0], group=int(fields[2]), start=int(fields[19])))
        return rows

    def exited(rows):
        return all(t['state'] in {'Z', 'X', 'x'} for t in rows)

    def probe(c):
        path = c.base + '/state/instance.lock'
        before = execute(f"stat -c '%d:%i:%s:%u:%a' {path}", '1000:1000').stdout.strip()
        reply = execute(f'flock -n -E 73 {path} true', '1000:1000', check=False)
        assert reply.returncode in (0, 73)
        assert execute(f"stat -c '%d:%i:%s:%u:%a' {path}", '1000:1000').stdout.strip() == before
        return dict(exit_code=reply.returncode, contended=reply.returncode == 73, identity=before)

    def competitors(c):
        rows = []
        path = output / (c.label + '-competitor.json')
        path.write_text(json.dumps(dict(c.config, bind='127.0.0.1:0')), encoding='utf-8')
        remote = c.base + '/competitor.json'
        run(['cp', str(path), client + ':' + remote])
        for index, command in enumerate(('', '--initialize-source ', '--transfer-one ')):
            name = c.label + '-competitor-' + str(index)
            tail = ' 1' if command == '--transfer-one ' else ''
            began = time.monotonic()
            process = spawn(f'exec {c.binary} {command}{remote}{tail}', name)
            c.processes.append(process)
            assert process.wait(timeout=6) != 0
            log = (output / (name + '.log')).read_text(encoding='utf-8')
            assert 'local instance or surviving worker already owns state' in log, log
            rows.append(dict(command=command.strip() or 'alternate_port_service', refused=True,
                             seconds=round(time.monotonic() - began, 3), diagnostic=log.strip()))
        return rows

    for profile in ('debug', 'release'):
        for point in ('bootstrap_enrolled', 'bootstrap_populated'):
            for phase in ('blocked', 'terminating'):
                c = None
                result = dict(profile=profile, point=point, death_phase=phase, repetition=0, passed=False)
                try:
                    c = Case(profile, point, shutdown=True, shutdown_wait=2,
                             suffix='-ds-' + phase, both_nfs=True,
                             separate_exports=True, independent_endpoints=True)
                    c.result.update(result)
                    result = c.result
                    result.update(scenario_id='SC-096', supporting_scenarios=['SC-013', 'SC-018', 'SC-034', 'SC-036', 'SC-092', 'SC-093', 'SC-095'],
                                  failed_endpoint='destination',
                                  boundary='early delivery after source bootstrap and enrollment')
                    prepare(c, execute, status, both_nfs=True)
                    result['endpoint_outage'] = endpoints.stop('destination')
                    c.start(False)
                    began = time.monotonic()
                    result['ready_while_destination_unavailable'] = c.request('GET', '/healthz')
                    result['health_seconds'] = round(time.monotonic() - began, 3)
                    assert result['ready_while_destination_unavailable'][0] == 200 and result['health_seconds'] < 5
                    result['running_status'] = status(c, 'Running')
                    if point == 'bootstrap_enrolled':
                        assert result['running_status']['snapshot']['workers'] == []
                        result['idle_start_without_destination_worker'] = True
                    code, accepted = c.request('POST', '/api/v2/jobs', c.body)
                    assert code == 202 and accepted['job_id'] == '1' and accepted['source_paths_released']
                    result['acceptance_during_destination_outage'] = [code, accepted]
                    if point == 'bootstrap_enrolled':
                        execute(f"printf 'next recording' >{c.source}/current/nested/data.bin", '1000:1000')
                    main = c.service_pid()
                    worker = None
                    for _ in range(20):
                        local = status(c, 'Running')
                        children = c.children()
                        if len(children) == 1 and local['snapshot']['workers'] == [int(children[0])] and c.state(children[0]) == 'D':
                            worker = children[0]
                            break
                        time.sleep(.2)
                    assert worker, 'no single real blocked destination delivery worker observed'
                    c.worker = worker
                    command = execute(f"tr '\\000' ' ' </proc/{worker}/cmdline", '1000:1000').stdout
                    assert c.binary in command and '--internal-delivery-worker' in command
                    security = execute(f'cat /proc/{worker}/status', '1000:1000').stdout
                    fields = {k: v.strip() for line in security.splitlines() if ':' in line
                              for k, v in [line.split(':', 1)] if k in {'Uid', 'Gid', 'CapInh', 'CapPrm', 'CapEff', 'NoNewPrivs'}}
                    assert fields['Uid'].split() == ['1000'] * 4 and fields['Gid'].split() == ['1000'] * 4
                    assert all(int(fields[k], 16) == 0 for k in ('CapInh', 'CapPrm', 'CapEff')) and fields['NoNewPrivs'] == '1'
                    held = epoch(c)
                    assert held['group'] == int(main)
                    result.update(coordinator_pid=main, worker_epoch_before_death=held,
                                  blocked_worker=dict(pid=worker, state='D', command=command, fixture_pause=False,
                                    wait_channel=execute(f'cat /proc/{worker}/wchan', '1000:1000').stdout.strip(), security=fields))
                    result['healthy_source_while_blocked'] = endpoints.during('destination')
                    result['source_custody_while_blocked'] = source_evidence(c, execute)
                    result['local_files_while_running'] = local_evidence(c, execute, both_nfs=True)
                    began = time.monotonic()
                    result['job_while_destination_blocked'] = c.request('GET', '/api/v2/jobs/1')
                    result['job_status_seconds'] = round(time.monotonic() - began, 3)
                    code, job = result['job_while_destination_blocked']
                    assert result['job_status_seconds'] < 5 and code == 200 and job['state'] == 'Claimed'
                    assert job['details']['source_cleanup_enabled'] is False
                    assert job['details']['files'][0]['attempt'] == (1 if point == 'bootstrap_populated' else None)
                    result['claimed_replay_while_blocked'] = c.request('POST', '/api/v2/jobs', c.body)
                    assert result['claimed_replay_while_blocked'][0] == 202
                    assert result['claimed_replay_while_blocked'][1]['job_id'] == '1'
                    assert result['claimed_replay_while_blocked'][1]['source_paths_released']
                    assert c.state(worker) == 'D'
                    result['old_tasks_before_signal'] = tasks(main, worker)
                    if phase == 'terminating':
                        name = c.label + '-stop'
                        stop = spawn(f'exec {c.binary} --stop {c.config_path}', name)
                        c.processes.append(stop)
                        began = time.monotonic()
                        stop.wait(timeout=10)
                        replies = [json.loads(line) for line in (output / (name + '.log')).read_text(encoding='utf-8').splitlines() if line.startswith('{')]
                        assert len(replies) == 1
                        value = replies[0]
                        result['stop'] = dict(exit_code=stop.returncode, seconds=round(time.monotonic() - began, 3), snapshot=value)
                        assert value['shutdown_wait_seconds'] == 2
                        if value['phase'] == 'Stopped':
                            assert stop.returncode == 0 and c.service.wait(timeout=5) == 0
                            assert exited(tasks(main, worker))
                            result['outcome'] = 'prompt_exit_before_coordinator_kill'
                        else:
                            assert stop.returncode == 2 and value['phase'] == 'ShutdownIncomplete' and value['shutdown_remaining_ms'] == 0
                            assert c.service.poll() is None and c.state(worker) == 'D'
                    if 'outcome' not in result:
                        c.signal(main, 'KILL')
                        result['coordinator_exit_code'] = c.service.wait(timeout=10)
                        assert result['coordinator_exit_code'] != 0
                        observations = result['orphan_samples'] = []
                        for _ in range(3):
                            row = dict(old_tasks=tasks(main, worker), worker_state=c.state(worker), guard=probe(c),
                                       local=status(c), epoch=epoch(c))
                            observations.append(row)
                            assert row['worker_state'] == 'D' and not exited(row['old_tasks'])
                            assert row['local']['exit_code'] == 2 and row['local']['snapshot']['phase'] == 'OwnerUnavailable'
                            assert row['epoch'] == held and c.state(worker) == 'D'
                            time.sleep(.5)
                        result['competitors_after_death'] = competitors(c)
                        assert c.state(worker) == 'D' and status(c, 'OwnerUnavailable')['exit_code'] == 2
                        result['healthy_source_while_orphan_blocked'] = endpoints.during('destination')
                        assert c.state(worker) == 'D'
                        result['outcome'] = 'blocked_orphan_retains_ownership' if phase == 'blocked' else 'terminating_orphan_retains_ownership'
                    assert epoch(c) == held
                    result['epoch_preserved_until_old_exit'] = True
                    restore()
                    c.await_exit(main)
                    result['worker_exit_after_restore'] = c.await_exit(worker)
                    for _ in range(30):
                        old = tasks(main, worker)
                        if exited(old):
                            break
                        time.sleep(.2)
                    else:
                        raise AssertionError('old process threads still live after restoration')
                    result['old_tasks_after_restore'] = old
                    result['old_threads_confirmed_exited'] = True
                    c.worker = None
                    result['local_status_after_exit'] = status(c, 'NoActiveOwner')
                    result['source_custody_after_exit'] = source_evidence(c, execute)
                    assert result['source_custody_after_exit'] == result['source_custody_while_blocked']
                    result['local_files_after_old_exit'] = local_evidence(c, execute, both_nfs=True)
                    result['destination_after_old_exit'] = destination_evidence(c, execute)
                    execute(f'test ! -e {c.destination}/1/COMMITTED.json; test ! -e {c.destination}/1/nested/data.bin', '1000:1000')
                    if point == 'bootstrap_populated':
                        assert partial_evidence(c, execute) == result['seed_partial']
                    recovered = c.recover()
                    assert recovered['details']['files'][0]['attempt'] == (2 if point == 'bootstrap_populated' else 1)
                    assert recovered['details']['source_cleanup_enabled'] is False
                    replacement = epoch(c)
                    assert replacement['group'] == int(c.service_pid()) and replacement['group'] != held['group']
                    assert all(replacement[k] == held[k] for k in ('version', 'boot', 'namespace', 'guard'))
                    result['worker_epoch_after_recovery'] = replacement
                    result['database_identity_after_recovery'] = execute(f"stat -c '%d:%i' {c.base}/state/jobs.sqlite", '1000:1000').stdout
                    assert result['database_identity_after_recovery'] == result['database_identity_before']
                    result['enrollment_receipt_after_recovery'] = receipt_evidence(c, execute)
                    assert result['enrollment_receipt_after_recovery'] == result['enrollment_receipt_before']
                    assert execute(f'cat {c.source}/current/nested/data.bin', '1000:1000').stdout == 'next recording'
                    c.verify()
                    recovered_both(c, execute)
                    if point == 'bootstrap_populated':
                        result['partial_after_recovery'] = partial_evidence(c, execute)
                        assert result['partial_after_recovery'] == result['seed_partial']
                    result.update(original_state_recovery=True, original_database_inode_preserved=True,
                                  producer_reused_path_preserved=True, re_enrollment_performed=False, passed=True)
                except Exception as error:
                    result.update(error=f'{type(error).__name__}: {error}', traceback=traceback.format_exc())
                finally:
                    if c:
                        try:
                            c.cleanup()
                            result['final_status'] = status(c, 'NoActiveOwner')
                            assert result['final_status']['exit_code'] == 0
                        except Exception as error:
                            result.update(cleanup_error=str(error), passed=False)
                    results.append(result)
                    print(f"NFS destination startup {profile}/{point}/{phase}: {'PASS' if result.get('passed') else 'FAILED'} ({result.get('outcome', result.get('error'))})", flush=True)
                if not result.get('passed'):
                    return dict(passed=False, scope='destination-startup')
    return dict(passed=len(results) == 8 and all(c['passed'] for c in results), scope='destination-startup',
                core_cases=len(results), raw_lock_closure_required=False,
                blocked_orphan_cases=sum(c['outcome'] == 'blocked_orphan_retains_ownership' for c in results),
                terminating_orphan_cases=sum(c['outcome'] == 'terminating_orphan_retains_ownership' for c in results),
                prompt_exit_cases=sum(c['outcome'] == 'prompt_exit_before_coordinator_kill' for c in results))
