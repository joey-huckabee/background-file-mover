"""Selected unlink syscall and pre-directory-sync deaths, never power-loss proof."""
import json
import time
import traceback
from nfs_publication import objects, same_object
from nfs_both import before, recovered


def qualify(Case, run, execute, spawn, restore, output, client, results, endpoints):
    def status(c, phase):
        began = time.monotonic()
        reply = execute(f'{c.binary} --status {c.config_path}', '1000:1000', check=False)
        value = json.loads(reply.stdout)
        row = dict(exit_code=reply.returncode, seconds=round(time.monotonic() - began, 3), snapshot=value)
        assert row['seconds'] < 5 and value['phase'] == phase, row
        assert reply.returncode == (2 if phase == 'OwnerUnavailable' else 0), row
        return row

    def tasks(main, worker):
        rows = execute(f'for f in /proc/{main}/task/*/stat /proc/{worker}/task/*/stat; do '
                       'test ! -r "$f" || cat "$f" 2>/dev/null || true; done', '1000:1000').stdout.splitlines()
        return [dict(tid=int(r.split()[0]), state=r.rsplit(') ', 1)[1].split()[0]) for r in rows]

    for profile in ('debug', 'release'):
        for point in ('file_link_sync', 'file_unlink', 'file_unlink_sync',
                      'manifest_link_sync', 'manifest_unlink', 'manifest_unlink_sync'):
            c = None
            result = dict(profile=profile, point=point, passed=False, scenario_id='SC-097')
            try:
                c = Case(profile, point, both_nfs=True, separate_exports=True, independent_endpoints=True)
                c.result.update(result)
                result = c.result
                assert len(c.base + '/state/control.sock') < 108
                c.start(True)
                code, accepted = c.request('POST', '/api/v2/jobs', c.body)
                assert code == 202 and accepted['source_paths_released']
                execute(f"printf 'next recording' >{c.source}/current/nested/data.bin", '1000:1000')
                c.await_pause()
                main, worker = c.service_pid(), c.worker
                security = execute(f'cat /proc/{worker}/status', '1000:1000').stdout
                fields = {k: v.strip() for line in security.splitlines() if ':' in line
                          for k, v in [line.split(':', 1)]
                          if k in {'Uid', 'Gid', 'CapInh', 'CapPrm', 'CapEff', 'NoNewPrivs'}}
                assert fields['Uid'].split() == fields['Gid'].split() == ['1000'] * 4
                assert all(int(fields[k], 16) == 0 for k in ('CapInh', 'CapPrm', 'CapEff'))
                assert fields['NoNewPrivs'] == '1'
                result['worker_security'] = fields
                manifest = point.startswith('manifest')
                active_old = '.staging/COMMITTED.part' if manifest else '.staging/1.part'
                active_new = 'COMMITTED.json' if manifest else 'nested/data.bin'
                before(c, execute)
                initial = objects(c, execute)
                result['publication_before_outage'] = initial
                expected = initial[active_new]
                assert expected is not None
                removed = point.endswith('unlink_sync')
                if removed:
                    assert initial[active_old] is None and expected['links'] == 1
                else:
                    assert initial[active_old] == expected and expected['links'] == 2
                payload = initial['nested/data.bin']
                assert payload['sha256'] == result['source_payload_before'][1].split()[0]
                if manifest:
                    assert initial['.staging/1.part'] is None and payload['links'] == 1
                else:
                    assert initial['COMMITTED.json'] is None and initial['.staging/COMMITTED.part'] is None
                job = c.request('GET', '/api/v2/jobs/1')[1]
                assert job['state'] == 'Claimed' and job['details']['source_cleanup_enabled'] is False
                assert job['details']['files'][0]['attempt'] == 1
                assert job['details']['files'][0]['transfer_phase'] == ('Published' if manifest else 'PublishIntent')
                result['job_before_death'] = job
                held = json.loads(execute(f'cat {c.base}/state/workers.json', '1000:1000').stdout)
                assert held['group'] == int(main)
                result['worker_epoch_before_death'] = held
                result['endpoint_outage'] = endpoints.stop('destination')
                actual_unlink = point.endswith('_unlink')
                if actual_unlink:
                    execute(f'umask 077; : >{c.rendezvous}/go', '1000:1000')
                    time.sleep(3)
                    assert c.state(worker) == 'D'
                    raw = execute(f'cat /proc/{worker}/syscall').stdout.strip()
                    fields = raw.split()
                    # Linux x86_64 unlinkat(dirfd, name, flags), not merely D state.
                    assert len(fields) == 9 and fields[0] == '263', raw
                    fd = int(fields[1], 16)
                    target = execute(f'readlink /proc/{worker}/fd/{fd}', '1000:1000').stdout.strip()
                    assert target == c.destination + '/1/.staging', target
                    assert int(fields[3], 16) == 0, raw
                    result['blocked_unlink_syscall'] = dict(raw=raw, fd=fd, parent=target)
                    result['interruption_kind'] = 'in_flight_unlinkat_syscall'
                else:
                    # Keep the local pause armed: namespace effect has returned,
                    # but the following directory/file sync has not been called.
                    assert execute(f'test ! -e {c.rendezvous}/go', '1000:1000', check=False).returncode == 0
                    result['interruption_kind'] = 'effect_returned_before_sync'
                result['healthy_source_during_outage'] = endpoints.during('destination')
                began = time.monotonic()
                assert c.request('GET', '/healthz')[0] == 200
                result['health_seconds'] = round(time.monotonic() - began, 3)
                began = time.monotonic()
                during = c.request('GET', '/api/v2/jobs/1')[1]
                result['job_status_seconds'] = round(time.monotonic() - began, 3)
                assert during['state'] == 'Claimed' and during['details']['files'] == job['details']['files']
                assert during['details']['manifest_phase'] == job['details']['manifest_phase']
                began = time.monotonic()
                replay = c.request('POST', '/api/v2/jobs', c.body)
                result['claimed_replay'] = replay
                result['replay_seconds'] = round(time.monotonic() - began, 3)
                assert replay[0] == 202 and replay[1]['job_id'] == '1' and replay[1]['source_paths_released']
                assert all(result[k] < 5 for k in ('health_seconds', 'job_status_seconds', 'replay_seconds'))
                assert c.children() == [worker]
                c.signal(main, 'KILL')
                assert c.service.wait(timeout=10) != 0
                if actual_unlink:
                    assert c.state(worker) == 'D'
                    result['orphan_status'] = status(c, 'OwnerUnavailable')
                    assert json.loads(execute(f'cat {c.base}/state/workers.json', '1000:1000').stdout) == held
                    # Different port forces the contender to reach the guard.
                    path = output / (c.label + '-competitor.json')
                    path.write_text(json.dumps(dict(c.config, bind='127.0.0.1:0')), encoding='utf-8')
                    remote = c.base + '/competitor.json'
                    run(['cp', str(path), client + ':' + remote])
                    contender = spawn(f'exec {c.binary} {remote}', c.label + '-competitor')
                    c.processes.append(contender)
                    assert contender.wait(timeout=6) != 0
                    diagnostic = (output / (c.label + '-competitor.log')).read_text(encoding='utf-8')
                    assert 'local instance or surviving worker already owns state' in diagnostic, diagnostic
                    result['alternate_port_contender_refused'] = diagnostic.strip()
                    assert c.state(worker) == 'D'
                c.signal(worker, 'KILL')
                result['worker_state_after_kill_before_restore'] = c.state(worker)
                restore()
                c.await_exit(main)
                result['worker_exit_after_restore'] = c.await_exit(worker)
                for _ in range(30):
                    old = tasks(main, worker)
                    if all(t['state'] in {'Z', 'X', 'x'} for t in old):
                        break
                    time.sleep(.2)
                else:
                    raise AssertionError('old process still has live threads')
                result['old_threads_before_recovery'] = old
                c.worker = None
                result['status_after_old_exit'] = status(c, 'NoActiveOwner')
                observed = objects(c, execute)
                result['publication_after_old_exit'] = observed
                same_object(observed[active_new], expected)
                aliases = [observed[n] for n in (active_old, active_new) if observed[n] is not None]
                for obj in aliases:
                    same_object(obj, expected)
                    assert obj['links'] == len(aliases)
                if removed:
                    assert observed[active_old] is None
                if not manifest:
                    assert observed['COMMITTED.json'] is None
                final = c.recover()
                assert final['details']['files'][0]['attempt'] == 1 and final['details']['source_cleanup_enabled'] is False
                c.verify()
                recovered(c, execute)
                after = objects(c, execute)
                result['publication_after_recovery'] = after
                same_object(after[active_new], expected)
                same_object(after['nested/data.bin'], payload)
                assert after['.staging/1.part'] is None and after['.staging/COMMITTED.part'] is None
                assert after['nested/data.bin']['links'] == after['COMMITTED.json']['links'] == 1
                assert execute(f'cat {c.source}/current/nested/data.bin', '1000:1000').stdout == 'next recording'
                assert execute(f'test ! -e {c.destination}/1/.staging/2.part', '1000:1000', check=False).returncode == 0
                result.update(original_state_recovery=True, original_publication_inode_preserved=True,
                              producer_reused_path_preserved=True, restart_only_after_restore_and_exit=True, passed=True)
            except Exception as error:
                result.update(error=f'{type(error).__name__}: {error}', traceback=traceback.format_exc())
            finally:
                if c:
                    try:
                        c.cleanup()
                        result['final_status'] = status(c, 'NoActiveOwner')
                    except Exception as error:
                        result.update(cleanup_error=str(error), passed=False)
                results.append(result)
                print(f"NFS publication sync {profile}/{point}: {'PASS' if result['passed'] else 'FAILED'}", flush=True)
            if not result['passed']:
                return dict(passed=False)
    return dict(passed=len(results) == 12 and all(c['passed'] for c in results),
                scope='publication-sync', core_cases=len(results),
                in_flight_unlink_cases=sum('blocked_unlink_syscall' in c for c in results),
                pre_sync_crash_cases=sum(c.get('interruption_kind') == 'effect_returned_before_sync' for c in results))
