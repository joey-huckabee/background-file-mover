"""Finite old-manager/hard-NFS cases; owned fixture only, no production enablement."""
import json
import time


class Lab:
    def __init__(self, raw, record):
        self.raw, self.record = raw, record
        self.network = self.volume = self.server = None
        self.network_created = self.volume_created = False
        self.mounts = []

    def create(self):
        image = 'localhost/background-file-mover-e2-nfs'
        self.record['server_image'] = json.loads(self.raw(['image', 'inspect', image]).stdout)[0]
        self.network = 'bfm-systemd-nfs-' + self.record['run_id'].removeprefix('systemd-').lower()
        self.volume = self.network + '-data'
        self.raw(['network', 'create', '--internal', self.network])
        self.network_created = True
        self.record['nfs_network'] = json.loads(self.raw(['network', 'inspect', self.network]).stdout)[0]
        assert self.record['nfs_network']['internal'] is True
        self.raw(['volume', 'create', self.volume])
        self.volume_created = True
        self.server = self.raw(['create', '--privileged', '--network', self.network,
                                '--volume', self.volume + ':/exports', image]).stdout.strip()
        self.record['nfs_resources'] = dict(network=self.network, volume=self.volume, server=self.server)
        self.raw(['start', self.server])
        for _ in range(40):
            if 'NFS_READY' in self.raw(['logs', self.server]).stdout:
                break
            time.sleep(.5)
        else:
            raise RuntimeError('owned NFS server did not become ready')
        data = json.loads(self.raw(['inspect', self.server]).stdout)[0]
        self.ip = data['NetworkSettings']['Networks'][self.network]['IPAddress']
        self.record['server_ip'] = self.ip
        self.record['server_packages'] = self.raw(['exec', self.server, 'dpkg-query', '-W']).stdout.splitlines()

    def mount(self, client, prefix, execute):
        from nfs_exports import prepare
        options = f'addr={self.ip},vers=4.1,proto=tcp,port=2049,hard,timeo=10,retrans=1,noac'

        def run(args, check=True, timeout=45):
            if args[:3] == ['exec', client, 'mount']:
                assert args[-1] in {'/tmp/nfs-source', '/tmp/nfs-destination'}
                args = prefix() + args[2:-1] + ['/sles' + args[-1]]
            return self.raw(args, check, timeout)

        self.record['nfs_exports'] = {}
        prepare(run, execute, self.server, client, self.ip, options, self.mounts, self.record['nfs_exports'])
        self.record['nfs_mount_options'] = options

    def restore(self):
        if self.server:
            self.raw(['exec', self.server, 'rpc.nfsd', '-G', '10', '-L', '10', '-V', '4', '-p', '2049', '2'])

    def outage(self):
        self.raw(['exec', self.server, 'rpc.nfsd', '0'])
        threads = self.raw(['exec', self.server, 'cat', '/proc/fs/nfsd/threads']).stdout.strip()
        assert threads == '0'
        return dict(nfsd_threads=threads, scope='joint outage of two exports on one controlled server')

    def unmount(self, host):
        self.restore()
        for _, path in reversed(self.mounts):
            host('umount /sles' + path, timeout=20)
        self.mounts.clear()

    def remove(self):
        if self.server:
            self.raw(['exec', self.server, 'rpc.nfsd', '0'], check=False)
            self.raw(['rm', '--force', self.server])
        if self.volume_created:
            self.raw(['volume', 'rm', self.volume])
        if self.network_created:
            self.raw(['network', 'rm', self.network])


def restart_while_blocked(c, held, old_tasks, exited, helpers):
    """Three requested sequences, bounded settling and a finite quiet window."""
    ctl, props = helpers['ctl'], helpers['props']
    lifecycle, epoch, journal = helpers['lifecycle'], helpers['epoch'], helpers['journal']
    began = time.monotonic()
    rows = c.result['incomplete_restart_observations'] = []
    requests = c.result['incomplete_restart_requests'] = []

    def sample():
        local = lifecycle(c)
        tasks = old_tasks()
        observed_epoch = epoch(c)
        text = journal(c.unit)
        counts = dict(guard_refusals=text.count('local instance or surviving worker already owns state'),
                      started=text.count('Started File mover lifecycle qualification'),
                      starting=text.count('Starting File mover lifecycle qualification'),
                      failed_start=text.count('Failed to start File mover lifecycle qualification'),
                      scheduled_restart=text.count('hold-off time over, scheduling restart'))
        row = dict(seconds=round(time.monotonic() - began, 3), local=local, old_tasks=tasks,
                   epoch=observed_epoch, manager=props(c.unit), journal_counts=counts)
        rows.append(row)
        assert not exited(tasks) and any(t['state'] == 'D' for t in tasks), row
        assert local['exit_code'] == 2 and local['snapshot']['phase'] in {'ShutdownIncomplete', 'OwnerUnavailable'}, row
        assert observed_epoch == held, row
        assert counts['guard_refusals'] <= 6, text
        assert counts['started'] <= 7 and counts['starting'] <= 7 and counts['scheduled_restart'] <= 6, text
        return row

    for index in range(3):
        # Space explicit requests beyond the fixture's ten-second rate window;
        # do not reset failed state while old workers survive.
        if index:
            previous = requests[-1]['seconds']
            while time.monotonic() - began - previous < 12:
                sample()
                time.sleep(1)
        request_began = time.monotonic()
        reply = ctl(f'start --no-block {c.unit}', check=False)
        request = dict(index=index + 1, seconds=round(request_began - began, 3),
                       exit_code=reply.returncode, stdout=reply.stdout, stderr=reply.stderr)
        requests.append(request)
        while time.monotonic() - request_began < 30:
            row = sample()
            jobs = ctl('list-jobs --no-legend').stdout
            row['manager_jobs'] = jobs
            if (row['manager']['ActiveState'] in {'failed', 'inactive'}
                    and row['manager']['MainPID'] == '0' and c.unit not in jobs):
                request['settled_seconds'] = round(time.monotonic() - request_began, 3)
                assert request['settled_seconds'] < 30
                request['manager_after'] = row['manager']
                request['journal_after'] = journal(c.unit)
                break
            time.sleep(1)
        else:
            raise AssertionError('explicit restart request did not settle within 30 seconds')
    c.result['competitors_after_restart_requests'] = helpers['refuse'](c)
    first = sample()
    quiet_began = time.monotonic()
    while time.monotonic() - began < 90 or time.monotonic() - quiet_began < 20:
        time.sleep(2)
        row = sample()
        assert row['journal_counts'] == first['journal_counts'], 'activation/refusal growth during quiet window'
        assert row['manager']['MainPID'] == '0' and row['manager']['ActiveState'] in {'failed', 'inactive'}
    c.result['restart_quiet_window'] = dict(seconds=round(time.monotonic() - quiet_began, 3),
        outage_after_incomplete_stop_seconds=round(time.monotonic() - began, 3),
        first=first, last=rows[-1], journal=journal(c.unit))


def exercise(c, kind, lab, host, execute, popen, client, helpers):
    from nfs_both import before, recovered
    ctl, props = helpers['ctl'], helpers['props']
    lifecycle, epoch = helpers['lifecycle'], helpers['epoch']
    helpers['start_unit'](c, pause='copy_chunk', timeout=8,
                          restart='no' if kind == 'nfs-stop' else 'on-failure')
    main = c.service_pid()
    assert c.request('POST', '/api/v2/jobs', c.body)[0] == 202
    execute(f"printf 'next recording' >{c.source}/current/nested/data.bin", '1000:1000')
    c.await_pause()
    before(c, execute)
    worker = c.worker
    c.result['worker_security'] = helpers['security'](c, worker)
    c.result['worker_cgroup'] = execute(f'cat /proc/{worker}/cgroup', '1000:1000').stdout
    assert c.unit in c.result['worker_cgroup']
    held = epoch(c)
    assert held['group'] == int(main)
    c.result['worker_epoch_before_outage'] = held

    def old_tasks():
        # Inspect every thread of both known processes, including a zombie
        # leader with a still-live thread. Read only local procfs during outage.
        script = f'for file in /proc/{main}/task/*/stat /proc/{worker}/task/*/stat; do test ! -r "$file" || cat "$file" 2>/dev/null || true; done'
        tasks = []
        for line in execute(script, '1000:1000').stdout.splitlines():
            prefix, fields = line.rsplit(') ', 1)
            fields = fields.split()
            tasks.append(dict(tid=int(prefix.split()[0]), state=fields[0], group=int(fields[2]), start=int(fields[19])))
        return tasks

    def exited(tasks):
        return all(t['state'] in {'Z', 'X', 'x'} for t in tasks)
    c.result['endpoint_outage'] = lab.outage()
    execute(f': >{c.rendezvous}/go', '1000:1000')
    for _ in range(15):
        if c.state(worker) == 'D':
            break
        time.sleep(.2)
    else:
        raise AssertionError('no actual hard-NFS D-state worker observed')
    c.result['blocked_worker'] = dict(pid=worker, state='D', pause_released=True,
        wait_channel=execute(f'cat /proc/{worker}/wchan', '1000:1000').stdout.strip())
    c.result['running_local_status'] = lifecycle(c, 'Running')
    c.result['competitors_before_signal'] = helpers['refuse'](c)
    host(f': >/run/{c.unit}.env')  # Subsequent launches must not pause.
    if kind in {'nfs-stop', 'nfs-restart'}:
        job = popen(['exec', client, 'systemctl', 'stop', c.unit], c.label + '-systemctl-stop')
        began = time.monotonic()
        reply = execute(f'LD_BIND_NOW=1 {c.binary} --stop {c.config_path}', '1000:1000', check=False)
        seconds = time.monotonic() - began
        assert seconds < 5 and reply.returncode in (0, 2), reply.stderr
        value = json.loads(reply.stdout)
        assert value['phase'] in {'Stopped', 'NoActiveOwner', 'ShutdownIncomplete'}
        if value['phase'] == 'ShutdownIncomplete':
            assert reply.returncode == 2 and value['shutdown_wait_seconds'] == 2 and value['shutdown_remaining_ms'] == 0
        else:
            assert reply.returncode == 0
        c.result['independent_stop_controller'] = dict(exit_code=reply.returncode, seconds=round(seconds, 3), snapshot=value)
        job.wait(timeout=25)
        assert time.monotonic() - began < 24 and job.returncode in (0, 1)
        c.result['manager_stop'] = dict(exit_code=job.returncode, seconds=round(time.monotonic() - began, 3), properties=props(c.unit))
        observation = lifecycle(c)
        tasks = old_tasks()
        c.result['old_tasks_after_stop'] = tasks
        if not exited(tasks):
            assert observation['snapshot']['phase'] == 'ShutdownIncomplete'
            assert observation['snapshot']['instance_id'] == c.result['running_local_status']['snapshot']['instance_id']
            assert epoch(c) == held
            c.result['outcome'] = 'incomplete-worker-retained'
            c.result['competitors_after_signal'] = helpers['refuse'](c)
        else:
            assert observation['snapshot']['phase'] == 'NoActiveOwner'
            assert c.state(main) in {'', 'Z'}
            c.result['outcome'] = 'prompt-kernel-assisted-exit'
        c.result['after_stop_status'] = observation
        if kind == 'nfs-restart':
            assert c.result['outcome'] == 'incomplete-worker-retained', 'restart qualification requires an actual surviving worker'
            restart_while_blocked(c, held, old_tasks, exited, helpers)
    else:
        ctl(f'kill --kill-who=main --signal=KILL {c.unit}')
        observations = []
        for _ in range(5):
            observation = lifecycle(c)
            old = dict(main=c.state(main), worker=c.state(worker))
            tasks = old_tasks()
            snapshot = observation['snapshot']
            if not exited(tasks):
                assert snapshot['phase'] == 'OwnerUnavailable' and epoch(c) == held
            if snapshot['phase'] == 'NoActiveOwner':
                assert exited(tasks)
            elif snapshot['coordinator_pid'] not in (None, int(main)):
                assert exited(tasks)
            else:
                assert snapshot['phase'] == 'OwnerUnavailable'
            observations.append(dict(local=observation, old_processes=old, old_tasks=tasks, manager=props(c.unit)))
            time.sleep(.2)
        c.result['restart_observations'] = observations
        c.result['restart_journal_during_outage'] = helpers['journal'](c.unit)
        c.result['outcome'] = 'authorized-replacement-after-old-exit' if any(
            o['local']['snapshot']['coordinator_pid'] not in (None, int(main)) for o in observations
        ) else 'old-exit-or-retained-exclusion-observed'
    c.result['restore_requested'] = True
    lab.restore()
    c.await_exit(main); c.await_exit(worker)
    for _ in range(30):
        tasks = old_tasks()
        if exited(tasks):
            break
        time.sleep(.2)
    else:
        raise AssertionError('old process threads still live after restoration')
    c.result['old_tasks_after_restore'] = tasks
    c.result['old_threads_confirmed_exited'] = True
    c.worker = None
    if kind == 'nfs-restart':
        observations = c.result['post_restore_observations'] = []
        began = time.monotonic()
        while True:
            local = lifecycle(c)
            tasks = old_tasks()
            assert exited(tasks)
            observations.append(dict(seconds=round(time.monotonic() - began, 3), local=local,
                                     old_tasks=tasks, manager=props(c.unit)))
            assert local['snapshot']['phase'] in {'NoActiveOwner', 'Starting', 'Running'}
            if time.monotonic() - began >= 10:
                break
            time.sleep(1)
        automatic = any(o['local']['snapshot']['phase'] in {'Starting', 'Running'} for o in observations)
        c.result['automatic_replacement_after_restore'] = automatic
        if automatic:
            assert observations[-1]['local']['snapshot']['phase'] == 'Running'
            assert epoch(c)['group'] != held['group']
            c.result['recovery_action'] = 'automatic replacement observed after confirmed old exit'
        else:
            assert all(o['local']['snapshot']['phase'] == 'NoActiveOwner' for o in observations)
            c.result['recovery_action'] = 'explicit reset-failed and start after restoration and confirmed old exit'
            helpers['start_unit'](c, restart='no', timeout=8)
    else:
        helpers['start_unit'](c, restart='no', timeout=8)
    c.recover(restart=False)
    assert c.result['recovered_status']['details']['files'][0]['attempt'] == 2
    assert c.result['recovered_status']['details']['source_cleanup_enabled'] is False
    replacement = epoch(c)
    assert replacement['group'] != held['group']
    assert all(replacement[key] == held[key] for key in ('version', 'boot', 'namespace', 'guard'))
    c.result['worker_epoch_after_recovery'] = replacement
    assert execute(f'cat {c.source}/current/nested/data.bin', '1000:1000').stdout == 'next recording'
    c.verify(); recovered(c, execute)
    c.result['original_state_recovery'] = True
    helpers['stop_unit'](c)
