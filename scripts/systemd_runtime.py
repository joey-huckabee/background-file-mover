"""Finite systemd/manual coordination checks, local payloads in a SLES chroot."""
import json
from pathlib import Path
import time
import traceback


def exercise(Case, host, execute, spawn, popen, output, client, report):
    template = (Path(__file__).parent / 'systemd/file-mover.service.in').read_text()
    counter = 0

    def ctl(command, check=True):
        return host('systemctl ' + command, check=check)

    def props(unit):
        keys = 'ActiveState,SubState,MainPID,ControlPID,ExecMainStatus,Result,NRestarts,User,Group,KillMode,SendSIGKILL,Restart,TimeoutStopUSec,RootDirectory'
        text = ctl(f'show {unit} --property={keys}').stdout
        return dict(line.split('=', 1) for line in text.splitlines() if '=' in line)

    def journal(unit):
        return host(f'journalctl -u {unit} --no-pager -o cat').stdout

    def install(c, restart='on-failure', pause=None, gate=False, timeout=75, other=False, alternate=False):
        unit = c.other if other else c.unit
        env = f'/run/{unit}.env'
        value = (f'FILE_MOVER_QUALIFICATION_PAUSE={pause}\nFILE_MOVER_QUALIFICATION_RENDEZVOUS={c.rendezvous}\n' if pause else '')
        host(f"cat >{env} <<'ENV'\n{value}ENV\nchmod 600 {env}")
        pregate = (f': >{c.base}/unit-armed; while test ! -e {c.base}/race-go; do sleep 0.01; done' if gate else 'true')
        text = template.format(binary=c.binary, config=c.alternate_config if alternate else c.config_path, envfile=env,
                               pregate=pregate, restart=restart, stop_timeout=timeout)
        local = output / unit
        local.write_text(text, encoding='utf-8')
        host(f"cat >/etc/systemd/system/{unit} <<'UNIT'\n{text}UNIT")
        ctl('daemon-reload')
        verification = host(f'systemd-analyze verify /etc/systemd/system/{unit}', check=False)
        assert verification.returncode == 0, verification.stderr
        assert 'Unknown' not in verification.stderr and 'Failed' not in verification.stderr, verification.stderr
        c.result.setdefault('units', []).append(dict(name=unit, text=text, verify=verification.stderr))

    def lifecycle(c, phase=None):
        began = time.monotonic()
        reply = execute(f'LD_BIND_NOW=1 {c.binary} --status {c.config_path}', '1000:1000', check=False)
        elapsed = time.monotonic() - began
        value = json.loads(reply.stdout)
        assert reply.returncode in (0, 2) and elapsed < 5, reply.stderr
        if phase:
            assert value['phase'] == phase, value
        return dict(exit_code=reply.returncode, seconds=round(elapsed, 3), snapshot=value)

    def security(c, pid):
        data = execute(f'cat /proc/{pid}/status', '1000:1000').stdout
        fields = {k: v.strip() for line in data.splitlines() if ':' in line
                  for k, v in [line.split(':', 1)] if k in {'Uid', 'Gid', 'CapInh', 'CapPrm', 'CapEff', 'NoNewPrivs'}}
        assert fields['Uid'].split() == ['1000'] * 4 and fields['Gid'].split() == ['1000'] * 4
        assert all(int(fields[k], 16) == 0 for k in ('CapInh', 'CapPrm', 'CapEff'))
        assert fields['NoNewPrivs'] == '1'
        return fields

    def mark(c, pid):
        assert str(pid).isdigit() and int(pid) > 0
        execute(f'printf {pid} >{c.marker}', '1000:1000')

    def ready(c, unit=True):
        for _ in range(30):
            if unit:
                p = props(c.unit)
                if p['MainPID'] != '0':
                    mark(c, p['MainPID'])
                if p['ActiveState'] == 'failed':
                    raise AssertionError(journal(c.unit))
            try:
                if c.request('GET', '/healthz')[0] == 200:
                    return
            except (RuntimeError, ValueError):
                pass
            time.sleep(.1)
        raise AssertionError('service did not become ready')

    def start_unit(c, **options):
        install(c, **options)
        ctl(f'reset-failed {c.unit}', check=False)
        ctl(f'start --no-block {c.unit}')
        ready(c)

    def stop_unit(c):
        began = time.monotonic()
        reply = ctl(f'stop {c.unit}', check=False)
        elapsed = time.monotonic() - began
        assert reply.returncode == 0 and elapsed < 15, reply.stderr
        assert props(c.unit)['MainPID'] == '0'
        assert lifecycle(c, 'NoActiveOwner')['exit_code'] == 0
        return dict(seconds=round(elapsed, 3), manager=props(c.unit))

    def refuse(c):
        rows = []
        for command, tail in [('', ''), ('--initialize-source ', ''), ('--transfer-one ', ' 1')]:
            began = time.monotonic()
            p = spawn(f'exec {c.binary} {command}{c.config_path}{tail}', c.label + '-refuse-' + str(len(c.processes)))
            c.processes.append(p)
            assert p.wait(timeout=8) != 0
            log = (output / (c.label + '-refuse-' + str(len(c.processes) - 1) + '.log')).read_text()
            assert ('local instance or surviving worker already owns state' in log or (not command and 'Address already in use' in log)), log
            rows.append(dict(command=command.strip() or 'service', seconds=round(time.monotonic() - began, 3), log=log))
        p = spawn(f'exec {c.binary} {c.alternate_config}', c.label + '-alternate-port')
        c.processes.append(p)
        assert p.wait(timeout=8) != 0
        log = (output / (c.label + '-alternate-port.log')).read_text()
        assert 'local instance or surviving worker already owns state' in log, log
        rows.append(dict(command='service_alternate_port_same_state', log=log))
        return rows

    def epoch(c):
        return json.loads(execute(f'cat {c.base}/state/workers.json', '1000:1000').stdout)

    def deliver(c):
        code, accepted = c.request('POST', '/api/v2/jobs', c.body)
        assert code == 202 and accepted['source_paths_released']
        execute(f"printf 'next recording' >{c.source}/current/nested/data.bin", '1000:1000')
        c.recover(restart=False)
        c.verify()
        assert c.result['recovered_status']['details']['source_cleanup_enabled'] is False

    def limit(c):
        for _ in range(30):
            p = props(c.unit)
            if (p['ActiveState'] == 'failed' and p['MainPID'] == '0'
                    and 'Start request repeated too quickly' in journal(c.unit)):
                break
            time.sleep(.25)
        else:
            raise AssertionError(journal(c.unit))
        text = journal(c.unit)
        refusals = text.count('local instance or surviving worker already owns state')
        assert 1 <= refusals <= 2 and p['MainPID'] == '0', (p, text)
        time.sleep(3)
        assert props(c.unit) == p and journal(c.unit).count('local instance or surviving worker already owns state') == refusals
        return dict(manager=p, guard_refusals=refusals, journal=text)

    def basic(c):
        start_unit(c)
        pid = props(c.unit)['MainPID']
        c.result['service_security'] = security(c, pid)
        assert lifecycle(c, 'Running')['snapshot']['shutdown_wait_seconds'] == 60
        c.result['manager_properties'] = props(c.unit)
        assert props(c.unit)['RootDirectory'] == '/sles' and props(c.unit)['User'] == 'mover'
        c.result['mapped_glibc'] = execute(f"grep 'libc-2.22.so' /proc/{pid}/maps", '1000:1000').stdout
        assert c.result['mapped_glibc']
        denied = execute(f'{c.binary} --status {c.config_path}', '1001:1001', check=False)
        assert denied.returncode != 0
        permission = host(f'systemctl --no-ask-password stop {c.unit}', user='1000:1000', check=False)
        assert permission.returncode != 0 and props(c.unit)['MainPID'] == pid
        c.result['permission_refusals'] = dict(foreign_uid=denied.stderr, unit_control=permission.stderr)
        deliver(c)
        c.result['manual_competitors'] = refuse(c)
        install(c, restart='no', other=True, alternate=True)
        ctl(f'start --no-block {c.other}')
        for _ in range(20):
            if props(c.other)['ActiveState'] == 'failed':
                break
            time.sleep(.1)
        assert 'local instance or surviving worker already owns state' in journal(c.other)
        assert props(c.unit)['MainPID'] == pid
        c.result['second_unit_refusal'] = journal(c.other)
        user_stop = execute(f'{c.binary} --stop {c.config_path}', '1000:1000')
        assert json.loads(user_stop.stdout)['phase'] == 'Stopped'
        stop_unit(c)
        c.start(False)
        manual_pid = c.service_pid()
        held = epoch(c)
        install(c, alternate=True)
        ctl(f'reset-failed {c.unit}', check=False)
        ctl(f'start --no-block {c.unit}')
        c.result['manual_owner_restart_limit'] = limit(c)
        assert epoch(c) == held and c.service.poll() is None
        c.signal(manual_pid, 'TERM'); assert c.service.wait(timeout=10) == 0
        c.result['races'] = []
        for round_index in range(2):
            execute(f'rm -f {c.base}/race-go {c.base}/unit-armed {c.base}/manual-armed', '1000:1000')
            install(c, restart='no', gate=True, alternate=True)
            ctl(f'reset-failed {c.unit}', check=False)
            ctl(f'start --no-block {c.unit}')
            name = c.label + '-race-' + str(round_index)
            manual = spawn(f': >{c.base}/manual-armed; while test ! -e {c.base}/race-go; do sleep 0.01; done; echo $$ >{c.marker}; exec {c.binary} {c.config_path}', name)
            c.processes.append(manual)
            for _ in range(30):
                if execute(f'test -f {c.base}/unit-armed && test -f {c.base}/manual-armed', '1000:1000', check=False).returncode == 0:
                    break
                time.sleep(.1)
            else:
                raise AssertionError('race launchers did not arm')
            execute(f': >{c.base}/race-go', '1000:1000')
            for _ in range(30):
                p = props(c.unit)
                unit_won = p['MainPID'] != '0' and p['ActiveState'] == 'active'
                manual_won = manual.poll() is None
                if unit_won != manual_won:
                    try:
                        c.request_port = 19879 if unit_won else 19878
                        if c.request('GET', '/healthz')[0] == 200:
                            break
                    except (RuntimeError, ValueError):
                        pass
                time.sleep(.1)
            else:
                raise AssertionError('race did not produce exactly one live winner')
            c.request_port = 19878
            owner = epoch(c)
            if unit_won:
                assert manual.wait(timeout=8) != 0
                assert 'local instance or surviving worker already owns state' in (output / (name + '.log')).read_text()
                assert owner['group'] == int(p['MainPID'])
                stop_unit(c)
            else:
                assert 'local instance or surviving worker already owns state' in journal(c.unit)
                assert owner['group'] == int(c.service_pid())
                c.signal(c.service_pid(), 'TERM'); assert manual.wait(timeout=10) == 0
            c.result['races'].append(dict(round=round_index, winner='unit' if unit_won else 'manual', epoch=owner))
        start_unit(c)
        c.result['clean_default_stop'] = stop_unit(c)
        c.start(False); c.signal(c.service_pid(), 'TERM'); assert c.service.wait(timeout=10) == 0
        c.verify()
        c.result['checks'] = ['identity_permissions_delivery', 'unit_excludes_manual_and_second_unit',
                              'manual_owner_bounded_restart', 'two_simultaneous_start_races', 'clean_default_stop_and_restart']

    def incomplete(c):
        start_unit(c, pause='shutdown_drain', timeout=8)
        pid = props(c.unit)['MainPID']; held = epoch(c)
        p = popen(['exec', client, 'systemctl', 'stop', c.unit], c.label + '-systemctl-stop')
        began = time.monotonic()
        p.wait(timeout=25)
        elapsed = time.monotonic() - began
        assert p.returncode in (0, 1) and elapsed < 24
        stopped = lifecycle(c, 'ShutdownIncomplete')
        assert stopped['exit_code'] == 2 and stopped['snapshot']['shutdown_wait_seconds'] == 2
        assert stopped['snapshot']['shutdown_remaining_ms'] == 0 and epoch(c) == held and c.state(pid) not in {'', 'Z'}
        assert '"ShutdownIncomplete"' in journal(c.unit)
        c.result['incomplete_stop'] = dict(seconds=round(elapsed, 3), systemctl_exit_code=p.returncode, manager=props(c.unit), controller=stopped)
        ctl(f'start {c.unit}', check=False)
        assert epoch(c) == held and c.state(pid) not in {'', 'Z'}
        c.result['competing_starts'] = refuse(c)
        install(c, restart='no', timeout=8)
        execute(f': >{c.rendezvous}/go', '1000:1000')
        c.await_exit(pid)
        assert lifecycle(c, 'NoActiveOwner')['exit_code'] == 0
        c.start(False); deliver(c)
        c.signal(c.service_pid(), 'TERM'); assert c.service.wait(timeout=10) == 0

    def orphan(c, managed):
        from nfs_both import before, recovered
        if managed:
            start_unit(c, pause='copy_chunk', timeout=8)
        else:
            c.start(True)
        main = c.service_pid()
        assert c.request('POST', '/api/v2/jobs', c.body)[0] == 202
        execute(f"printf 'next recording' >{c.source}/current/nested/data.bin", '1000:1000')
        c.await_pause(); before(c, execute)
        worker = c.worker
        c.result['worker_security'] = security(c, worker)
        c.result['worker_cgroup'] = execute(f'cat /proc/{worker}/cgroup', '1000:1000').stdout
        c.signal(worker, 'STOP'); assert c.state(worker) == 'T'
        held = epoch(c)
        if managed:
            assert c.unit in c.result['worker_cgroup']
            # Root-owned fixture environment changes only the next launch.
            host(f': >/run/{c.unit}.env')
            ctl(f'kill --kill-who=main --signal=KILL {c.unit}')
            for _ in range(40):
                p = props(c.unit)
                if p['MainPID'] not in {'0', main}:
                    assert c.state(worker) in {'', 'Z'} and c.state(main) in {'', 'Z'}
                    c.result['old_exit_before_new_main'] = True
                    break
                time.sleep(.1)
            else:
                raise AssertionError(journal(c.unit))
            c.worker = None
            ready(c)
        else:
            c.signal(main, 'KILL'); assert c.service.wait(timeout=10) != 0
            assert c.state(worker) == 'T' and lifecycle(c, 'OwnerUnavailable')['exit_code'] == 2
            install(c, alternate=True)
            ctl(f'start --no-block {c.unit}')
            c.result['orphan_restart_limit'] = limit(c)
            assert epoch(c) == held and c.state(worker) == 'T'
            c.result['orphan_competitors'] = refuse(c)
            assert lifecycle(c, 'OwnerUnavailable')['exit_code'] == 2
            execute(f': >{c.rendezvous}/go', '1000:1000')
            c.signal(worker, 'CONT'); c.await_exit(worker); c.worker = None
            assert lifecycle(c, 'NoActiveOwner')['exit_code'] == 0
            start_unit(c)
        c.recover(restart=False)
        assert c.result['recovered_status']['details']['files'][0]['attempt'] == 2
        assert epoch(c)['group'] != held['group']
        assert execute(f'cat {c.source}/current/nested/data.bin', '1000:1000').stdout == 'next recording'
        c.verify(); recovered(c, execute)
        c.result['original_state_recovery'] = True
        stop_unit(c)

    for production in (False, True):
        for profile in ('debug', 'release'):
            kinds = ['basic'] if production else ['incomplete', 'manual-orphan', 'managed-crash', 'basic']
            for kind in kinds:
                c = None
                try:
                    counter += 1
                    c = Case(profile, 'copy_chunk', production=production, local_only=True,
                             shutdown=kind == 'incomplete', shutdown_wait=2 if kind == 'incomplete' else None,
                             suffix='-sd-' + str(counter))
                    c.unit = 'fm-sd-' + str(counter) + '.service'
                    c.other = 'fm-sd-' + str(counter) + '-other.service'
                    alternate = dict(c.config, bind='127.0.0.1:19879')
                    c.alternate_config = c.base + '/alternate-port.json'
                    execute("cat >" + c.alternate_config + " <<'CONFIG'\n" + json.dumps(alternate) + "\nCONFIG", '1000:1000')
                    c.result['contention_probe'] = 'same state/source/destination; alternate bind 19879 to reach guard rather than occupied REST port'
                    c.result.update(kind=kind, unit=c.unit, scenario_id='SC-092')
                    c.result['database_inode_before'] = execute(f'stat -c %d:%i {c.base}/state/jobs.sqlite', '1000:1000').stdout
                    if kind == 'basic': basic(c)
                    elif kind == 'incomplete': incomplete(c)
                    else: orphan(c, managed=kind == 'managed-crash')
                    c.result['database_inode_after'] = execute(f'stat -c %d:%i {c.base}/state/jobs.sqlite', '1000:1000').stdout
                    assert c.result['database_inode_after'] == c.result['database_inode_before']
                    c.result['passed'] = True
                except Exception as error:
                    if c is None:
                        c = type('Failure', (), {'result': dict(profile=profile, production=production, kind=kind, passed=False), 'unit': '', 'other': ''})()
                    c.result.update(error=f'{type(error).__name__}: {error}', traceback=traceback.format_exc())
                finally:
                    if hasattr(c, 'base'):
                        try:
                            # Only fixture units/processes; release local pauses before stopping.
                            host(f"sed -i 's/Restart=on-failure/Restart=no/' /etc/systemd/system/{c.unit} /etc/systemd/system/{c.other} 2>/dev/null || true")
                            ctl('daemon-reload')
                            execute(f': >{c.rendezvous}/go', '1000:1000')
                            if c.worker and c.state(c.worker) not in {'', 'Z'}:
                                c.signal(c.worker, 'CONT'); c.signal(c.worker, 'TERM')
                            ctl(f'stop --no-block {c.unit} {c.other}', check=False)
                            if c.service and c.service.poll() is None:
                                c.signal(c.service_pid(), 'TERM')
                            for p in c.processes: p.wait(timeout=12)
                            ctl(f'stop {c.unit} {c.other}', check=False)
                            c.result['journals'] = {u: journal(u) for u in (c.unit, c.other)}
                            c.result['final_status'] = lifecycle(c, 'NoActiveOwner')
                        except Exception as error:
                            c.result.update(cleanup_error=str(error), passed=False)
                    report['cases'].append(c.result)
                    print(f"systemd {profile}/{'production' if production else 'qualification'}/{kind}: {'PASS' if c.result.get('passed') else 'FAILED'}", flush=True)
                if not c.result.get('passed'):
                    raise AssertionError(c.result.get('error', c.result.get('cleanup_error')))

