"""Fixture transport recovery with an OS probe; no live mover or NAS durability claim."""
import time
import subprocess


def qualify(relay, endpoints, run, execute, spawn, output, result):
    result.update(passed=False, scope='OS-only source NFSD thread stop/restart through the relay, not server reboot or live-mover recovery')
    server = endpoints.servers['source']
    path = endpoints.mounts['source'] + '/relay-restart-sentinel'
    pidfile = '/tmp/relay-restart-probe.pid'
    command = 'sha256sum ' + path
    process = None

    def restore():
        run(['exec', server, 'rpc.nfsd', '-G', '10', '-L', '10', '-V', '4', '-p', '2049', '2'])

    try:
        execute(f"umask 077; printf 'relay restart sentinel' >{path}", '1000:1000')
        expected = execute(command, '1000:1000').stdout.split()[0]
        result['expected_sha256'] = expected
        run(['exec', server, 'rpc.nfsd', '0'])
        result['threads_during_outage'] = {role:run(['exec',target,'cat','/proc/fs/nfsd/threads']).stdout.strip()
                                            for role,target in endpoints.servers.items()}
        assert result['threads_during_outage'] == dict(source='0', destination='2')
        process = spawn(f'echo $$ >{pidfile}; exec {command}', 'relay-restart-probe')
        for _ in range(30):
            value = execute('cat ' + pidfile, '1000:1000', check=False)
            if value.returncode == 0 and value.stdout.strip().isdigit():
                pid = value.stdout.strip()
                stat = execute(f'cat /proc/{pid}/stat', '1000:1000', check=False)
                if stat.returncode == 0 and stat.stdout.rsplit(') ',1)[1].split()[0] == 'D':
                    break
            assert process.poll() is None, 'probe did not block in real NFS'
            time.sleep(.1)
        else:
            raise AssertionError('actual D-state probe not observed')
        observed = execute(f"tr '\\000' ' ' </proc/{pid}/cmdline", '1000:1000').stdout.strip()
        assert observed == command and process.poll() is None
        result['pending_client'] = dict(pid=pid, command=observed, state='D')
        result['relay_during_outage'] = relay.state()
        assert any(e['kind'] in {'backend_closed','backend_connect_failed'}
                   for e in result['relay_during_outage']['transport_events']), 'backend disconnect path not exercised'
        result['healthy_destination'] = endpoints.healthy('destination')
        restore()
        began = time.monotonic()
        assert process.wait(timeout=60) == 0
        result['completion_seconds_after_restore'] = round(time.monotonic()-began,3)
        text = (output/'relay-restart-probe.log').read_text(encoding='utf-8')
        assert text.split() == [expected,path]
        result['probe_result'] = text
        result['healthy_source_after_restore'] = endpoints.healthy('source')
        result['relay_after_restore'] = relay.state()
        assert 0 <= result['relay_after_restore']['active'] <= 16
        assert result['relay_after_restore']['connections'] <= 400
        result['passed'] = True
        print('NFS relay backend stop/restart: PASS (actual pending source probe resumed)',flush=True)
        return result
    finally:
        restore()
        relay.release()
        if process is not None:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pid = execute('cat '+pidfile,'1000:1000').stdout.strip()
                assert pid.isdigit()
                observed = execute(f"tr '\\000' ' ' </proc/{pid}/cmdline",'1000:1000').stdout.strip()
                assert observed == command
                execute(f'kill -KILL {pid}','1000:1000')
                process.wait(timeout=10)
