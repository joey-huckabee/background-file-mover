"""Owned relay provisioning and real-server proof, no production network changes."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid


class ReplyRelay:
    def __init__(self, run, network, image, backend, containers, output):
        self.run, self.output = run, output
        self.counter = 0
        self.container = run(['create', '--network', network, '--cap-drop', 'all',
                              '--sysctl', 'net.ipv4.ip_unprivileged_port_start=0',
                              '--security-opt', 'no-new-privileges', '--user', '1000:1000',
                              '--entrypoint', '/usr/bin/python3', image,
                              '/tmp/nfs_reply_proxy.py', backend]).stdout.strip()
        containers.append(self.container)
        files = ('nfs_rpc.py', 'nfs_reply_proxy.py')
        for name in files:
            run(['cp', str(Path(__file__).parent / name), self.container + ':/tmp/' + name])
        run(['start', self.container])
        self.address = json.loads(run(['inspect', self.container]).stdout)[0]['NetworkSettings']['Networks'][network]['IPAddress']
        for _ in range(30):
            value = run(['exec', self.container, 'cat', '/tmp/control/state.json'], check=False)
            if value.returncode == 0 and json.loads(value.stdout).get('ready'):
                break
            time.sleep(.1)
        else:
            raise RuntimeError('reply relay did not become ready')
        self.evidence = dict(container=self.container, ip=self.address, backend=backend, image=image,
                             packages_added=False, ports_published=False,
                             private_netns_unprivileged_port_start=0, backend_source_ports='601-616',
                             drivers={n: hashlib.sha256((Path(__file__).parent / n).read_bytes()).hexdigest() for n in files})

    def state(self, strict=True):
        value = json.loads(self.run(['exec', self.container, 'cat', '/tmp/control/state.json']).stdout)
        if strict and value['errors']:
            raise AssertionError(value['errors'])
        return value

    def command(self, action, name=None):
        token = uuid.uuid4().hex
        self.counter += 1
        local = self.output / ('relay-command-' + str(self.counter) + '.json')
        local.write_text(json.dumps(dict(token=token, action=action, name=name)), encoding='utf-8')
        self.run(['cp', str(local), self.container + ':/tmp/control/command.next'])
        self.run(['exec', self.container, '/usr/bin/python3', '-c',
                  "import os; os.replace('/tmp/control/command.next','/tmp/control/command.json')"])
        for _ in range(20):
            state = self.state(strict=action != 'release')
            if state.get('command_token') == token:
                return state
            time.sleep(.1)
        raise AssertionError('relay command not acknowledged')

    def release(self):
        state = self.state(strict=False)
        return self.command('release') if state['armed'] else state

    def await_held(self):
        for _ in range(20):
            value = self.state()
            if value['held']:
                assert value['armed'] and not value['released'] and not value['dropped']
                # No target REMOVE success was forwarded in this armed window.
                assert not value['forwarded'], value
                for row in value['held']:
                    assert row['xid'] == row['request']['decoded']['xid'] == row['reply']['xid']
                    assert row['reply']['status'] == 0
                    assert dict(op=28, status=0) in row['reply']['operations']
                return value
            time.sleep(.2)
        raise AssertionError('no matched successful REMOVE reply was withheld')


def server_objects(run, server, old, final):
    assert all(c.isalnum() or c in '/._-' for c in old + final)
    script = ''
    for label, path in (('old', old), ('final', final)):
        script += (f"if test -e {path}; then printf '{label} '; stat -c '%d:%i:%h:%s' {path}; "
                   f"sha256sum {path}; else printf '{label} absent\\n'; fi; ")
    lines = iter(run(['exec', server, '/bin/sh', '-eu', '-c', script]).stdout.splitlines())
    result = {}
    for line in lines:
        label, value = line.split()
        if value == 'absent':
            result[label] = None
        else:
            device, inode, links, size = map(int, value.split(':'))
            result[label] = dict(device=device, inode=inode, links=links, size=size,
                                 sha256=next(lines).split()[0])
    assert set(result) == {'old', 'final'}
    return result


def preflight(relay, endpoints, run, execute, spawn, output, evidence):
    results = evidence['cases']
    server = endpoints.servers['destination']
    for mode in ('release', 'drop'):
        base = '/tmp/nfs-destination/reply-preflight-' + mode
        remote = '/exports/death-destination/reply-preflight-' + mode
        execute(f"umask 077; mkdir {base}; printf 'owned reply sentinel' >{base}/staging; ln {base}/staging {base}/final", '1000:1000')
        before = server_objects(run, server, remote + '/staging', remote + '/final')
        assert before['old'] == before['final'] and before['old']['links'] == 2
        armed = relay.command('arm', 'staging')
        pidfile = '/tmp/reply-preflight-' + mode + '.pid'
        process = spawn(f'echo $$ >{pidfile}; exec unlink {base}/staging', 'reply-preflight-' + mode)
        row = dict(mode=mode, passed=False, before=before, armed=armed)
        results.append(row)
        try:
            held = relay.await_held()
            row['held'] = held
            assert process.poll() is None
            pid = execute('cat ' + pidfile, '1000:1000').stdout.strip()
            assert pid.isdigit()
            process_state = execute(f'cat /proc/{pid}/stat', '1000:1000').stdout.rsplit(') ', 1)[1].split()[0]
            command = execute(f"tr '\\000' ' ' </proc/{pid}/cmdline", '1000:1000').stdout.strip()
            assert process_state == 'D' and command == 'unlink ' + base + '/staging'
            row['pending_client'] = dict(pid=pid, state=process_state, command=command)
            after = server_objects(run, server, remote + '/staging', remote + '/final')
            row['server_completed_while_withheld'] = after
            assert after['old'] is None and after['final']['links'] == 1
            for key in ('device', 'inode', 'size', 'sha256'):
                assert after['final'][key] == before['final'][key]
            observed = relay.state()
            assert observed['held'] and not observed['forwarded'] and process.poll() is None
            assert execute(f'cat /proc/{pid}/stat', '1000:1000').stdout.rsplit(') ', 1)[1].split()[0] == 'D'
            settled = relay.command(mode)
            row.update(before_release_or_drop=observed, settled=settled)
            assert process.wait(timeout=20) == 0
            final = relay.state()
            if mode == 'release':
                assert settled['released'] and not settled['dropped']
            else:
                assert settled['dropped'] and not settled['released']
                assert settled['connection_resets']
                assert final['forwarded'], 'discarded first reply was not followed by observed kernel replay'
                held_ids = {r['receive_id'] for r in settled['dropped']}
                assert not held_ids & {r['receive_id'] for r in final['forwarded']}
                identities = {json.dumps(r['request']['decoded']['operations'], sort_keys=True) for r in settled['dropped']}
                assert {json.dumps(r['request']['decoded']['operations'], sort_keys=True) for r in final['forwarded']} <= identities
                assert not {r['connection'] for r in settled['dropped']} & {r['connection'] for r in final['forwarded']}
            row.update(passed=True, before_release_or_drop=observed, settled=settled, final=final)
            print('NFS reply fixture ' + mode + ': PASS (server REMOVE success and missing old name while client waits)', flush=True)
        except Exception as error:
            row['error'] = f'{type(error).__name__}: {error}'
            raise
        finally:
            relay.release()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pid = execute('cat ' + pidfile, '1000:1000').stdout.strip()
                assert pid.isdigit()
                command = execute(f"tr '\\000' ' ' </proc/{pid}/cmdline", '1000:1000').stdout.strip()
                assert command == 'unlink ' + base + '/staging'
                execute(f'kill -KILL {pid}', '1000:1000')
                process.wait(timeout=10)
                row['cleanup_probe_terminated'] = True
    evidence['passed'] = len(results) == 2 and all(r['passed'] for r in results)
    return evidence
