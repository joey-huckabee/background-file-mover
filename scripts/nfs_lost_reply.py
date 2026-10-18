"""Worker recovery only after real-server reply-withholding capability passes."""
import json
import time
import traceback
from nfs_both import before, recovered
from nfs_publication import objects, same_object
from nfs_reply_relay import server_objects


def qualify(Case, run, execute, spawn, restore, output, client, results, endpoints, relay):
    def status(c, phase):
        began = time.monotonic()
        reply = execute(f'{c.binary} --status {c.config_path}', '1000:1000', check=False)
        value = json.loads(reply.stdout)
        row = dict(exit_code=reply.returncode, seconds=round(time.monotonic() - began, 3), snapshot=value)
        assert row['seconds'] < 5 and value['phase'] == phase, row
        assert reply.returncode == (2 if phase == 'OwnerUnavailable' else 0), row
        return row

    def tasks(main, worker):
        lines = execute(f'for f in /proc/{main}/task/*/stat /proc/{worker}/task/*/stat; do '
                        'test ! -r "$f" || cat "$f" 2>/dev/null || true; done', '1000:1000').stdout.splitlines()
        return [dict(tid=int(v.split()[0]), state=v.rsplit(') ', 1)[1].split()[0]) for v in lines]

    def exited(rows):
        return all(t['state'] in {'Z', 'X', 'x'} for t in rows)

    server = endpoints.servers['destination']
    for profile in ('debug', 'release'):
        for point in ('file_unlink', 'manifest_unlink'):
            c = None
            result = dict(profile=profile, point=point, passed=False, scenario_id='SC-098')
            try:
                c = Case(profile, point, suffix='-lr', both_nfs=True,
                         separate_exports=True, independent_endpoints=True)
                c.result.update(result)
                result = c.result
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
                old = '.staging/COMMITTED.part' if manifest else '.staging/1.part'
                final_name = 'COMMITTED.json' if manifest else 'nested/data.bin'
                before(c, execute)
                initial = objects(c, execute)
                result['publication_before_interception'] = initial
                expected, payload = initial[final_name], initial['nested/data.bin']
                assert initial[old] == expected and expected['links'] == 2
                remote = c.destination.replace('/tmp/nfs-destination/', '/exports/death-destination/', 1) + '/1/'
                original = server_objects(run, server, remote + old, remote + final_name)
                result['server_before'] = original
                assert original['old'] == original['final'] and original['final']['links'] == 2
                assert all(original['final'][k] == expected[k] for k in ('size', 'sha256'))
                job = c.request('GET', '/api/v2/jobs/1')[1]
                assert job['state'] == 'Claimed' and job['details']['source_cleanup_enabled'] is False
                assert job['details']['files'][0]['attempt'] == 1
                assert job['details']['files'][0]['transfer_phase'] == ('Published' if manifest else 'PublishIntent')
                result['job_before'] = job
                held_epoch = json.loads(execute(f'cat {c.base}/state/workers.json', '1000:1000').stdout)
                assert held_epoch['group'] == int(main)
                result['worker_epoch_before_death'] = held_epoch
                result['relay_armed'] = relay.command('arm', old.rsplit('/', 1)[1])
                execute(f'umask 077; : >{c.rendezvous}/go', '1000:1000')
                result['reply_withheld'] = relay.await_held()
                assert c.state(worker) == 'D'
                raw = execute(f'cat /proc/{worker}/syscall').stdout.strip()
                words = raw.split()
                assert len(words) == 9 and words[0] == '263', raw
                descriptor = int(words[1], 16)
                parent = execute(f'readlink /proc/{worker}/fd/{descriptor}', '1000:1000').stdout.strip()
                assert parent == c.destination + '/1/.staging' and int(words[3], 16) == 0
                result['blocked_unlink_syscall'] = dict(raw=raw, fd=descriptor, parent=parent)
                completed = server_objects(run, server, remote + old, remote + final_name)
                result['server_completed_with_reply_withheld'] = completed
                assert completed['old'] is None and completed['final']['links'] == 1
                assert all(completed['final'][k] == original['final'][k] for k in ('device', 'inode', 'size', 'sha256'))
                result['server_threads_while_withheld'] = {role: run(['exec', target, 'cat', '/proc/fs/nfsd/threads']).stdout.strip()
                                                         for role, target in endpoints.servers.items()}
                assert set(result['server_threads_while_withheld'].values()) == {'2'}
                result['healthy_source'] = endpoints.healthy('source')
                result['healthy_destination'] = endpoints.healthy('destination')
                for key, method, path, body in (('health', 'GET', '/healthz', None),
                                                 ('job', 'GET', '/api/v2/jobs/1', None),
                                                 ('replay', 'POST', '/api/v2/jobs', c.body)):
                    began = time.monotonic()
                    response = c.request(method, path, body)
                    result[key] = dict(seconds=round(time.monotonic() - began, 3), response=response)
                    assert result[key]['seconds'] < 5
                assert result['health']['response'][0] == 200
                during = result['job']['response'][1]
                assert during['state'] == 'Claimed' and during['details']['files'] == job['details']['files']
                assert during['details']['manifest_phase'] == job['details']['manifest_phase']
                replay = result['replay']['response']
                assert replay[0] == 202 and replay[1]['job_id'] == '1' and replay[1]['source_paths_released']
                assert c.children() == [worker] and c.state(worker) == 'D'
                result['relay_before_coordinator_death'] = relay.await_held()
                c.signal(main, 'KILL')
                assert c.service.wait(timeout=10) != 0
                old_tasks = tasks(main, worker)
                result['old_tasks_after_coordinator_death'] = old_tasks
                if not exited(old_tasks):
                    result['orphan_status'] = status(c, 'OwnerUnavailable')
                    assert json.loads(execute(f'cat {c.base}/state/workers.json', '1000:1000').stdout) == held_epoch
                    path = output / (c.label + '-competitor.json')
                    path.write_text(json.dumps(dict(c.config, bind='127.0.0.1:0')), encoding='utf-8')
                    remote_config = c.base + '/competitor.json'
                    run(['cp', str(path), client + ':' + remote_config])
                    process = spawn(f'exec {c.binary} {remote_config}', c.label + '-competitor')
                    c.processes.append(process)
                    assert process.wait(timeout=6) != 0
                    diagnostic = (output / (c.label + '-competitor.log')).read_text(encoding='utf-8')
                    assert 'local instance or surviving worker already owns state' in diagnostic
                    result['contender_refused'] = diagnostic.strip()
                    result['outcome'] = 'surviving_worker_excludes_replacement'
                    c.signal(worker, 'KILL')
                else:
                    result['outcome'] = 'worker_exited_after_coordinator_death'
                result['reply_discarded'] = relay.command('drop')
                assert result['reply_discarded']['dropped'] and not result['reply_discarded']['released']
                assert result['reply_discarded']['connection_resets']
                dropped_ids = {v['receive_id'] for v in result['reply_discarded']['dropped']}
                # A replay can arrive immediately after the explicit reset;
                # it must never be confused with forwarding a held frame.
                assert not dropped_ids & {v['receive_id'] for v in result['reply_discarded']['forwarded']}
                c.await_exit(main)
                result['worker_exit'] = c.await_exit(worker)
                for _ in range(30):
                    old_tasks = tasks(main, worker)
                    if exited(old_tasks):
                        break
                    time.sleep(.2)
                else:
                    raise AssertionError('old threads still live')
                result['old_threads_before_recovery'] = old_tasks
                c.worker = None
                result['status_after_old_exit'] = status(c, 'NoActiveOwner')
                observed = objects(c, execute)
                result['publication_after_old_exit'] = observed
                assert observed[old] is None
                same_object(observed[final_name], expected)
                final = c.recover()
                assert final['details']['files'][0]['attempt'] == 1 and final['details']['source_cleanup_enabled'] is False
                c.verify()
                recovered(c, execute)
                observed = objects(c, execute)
                result['publication_after_recovery'] = observed
                same_object(observed[final_name], expected)
                same_object(observed['nested/data.bin'], payload)
                assert observed['.staging/1.part'] is None and observed['.staging/COMMITTED.part'] is None
                assert observed['nested/data.bin']['links'] == observed['COMMITTED.json']['links'] == 1
                assert execute(f'cat {c.source}/current/nested/data.bin', '1000:1000').stdout == 'next recording'
                assert execute(f'test ! -e {c.destination}/1/.staging/2.part', '1000:1000', check=False).returncode == 0
                result.update(relay_after_recovery=relay.state(), original_state_recovery=True,
                              original_publication_inode_preserved=True, producer_reused_path_preserved=True, passed=True)
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
                print(f"NFS lost reply {profile}/{point}: {'PASS' if result['passed'] else 'FAILED'}", flush=True)
            if not result['passed']:
                return dict(passed=False)
    return dict(passed=len(results) == 4 and all(c['passed'] for c in results), scope='lost-reply', core_cases=len(results))
