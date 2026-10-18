"""Private systemd manager, unchanged SLES root, finite local lifecycle matrix."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / 'scripts/rust-platform.json').read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('gate', type=Path)
    parser.add_argument('--qualification-gate', type=Path, required=True)
    parser.add_argument('--connection', default='podman-machine-default-root')
    args = parser.parse_args()
    gates = [args.gate.resolve(), args.qualification_gate.resolve()]
    inventory = {p.relative_to(ROOT / 'rust').as_posix() for child in (ROOT / 'rust').iterdir()
                 if child.name not in {'validation', 'target'}
                 for p in (child.rglob('*') if child.is_dir() else [child]) if p.is_file()}
    reports = []
    for gate, mode in zip(gates, ['production', 'nfs-qualification']):
        report = json.loads((gate / 'report.json').read_text())
        assert report['status'] == 'PASSED' and report['config'] == CONFIG and report['build_mode'] == mode
        with tarfile.open(gate / 'source.tar.gz') as archive:
            assert {m.name for m in archive.getmembers() if m.isfile()} == inventory
            for m in archive.getmembers():
                if m.isfile():
                    target = (ROOT / 'rust' / m.name).resolve()
                    assert target.is_relative_to(ROOT / 'rust') and target.read_bytes() == archive.extractfile(m).read()
        reports.append(report)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    output = ROOT / 'rust/validation' / ('systemd-' + stamp)
    output.mkdir()
    record = dict(status='FAILED', run_id=output.name, gate=gates[0].name,
                  qualification_gate=gates[1].name, cases=[], cleanup_errors=[],
                  scope='systemd 252 manager outside pinned SLES root; local payload/state only; no native SLES-systemd, hard-NFS/systemd, reboot, persistence or authorization-policy approval')
    engine = ['podman', '--connection', args.connection]
    client = None
    tasks = []

    def raw(arguments, check=True, timeout=45):
        result = subprocess.run(engine + arguments, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=timeout)
        if check and result.returncode:
            raise RuntimeError(f'{arguments}: {result.stdout}{result.stderr}')
        return result

    def run(arguments, check=True, timeout=45):
        # Existing Case paths are absolute inside the SLES root, including cp.
        mapped = [a.replace(client + ':/', client + ':/sles/', 1)
                  if client and a.startswith(client + ':/') else a for a in arguments]
        return raw(mapped, check, timeout)

    def host(script, check=True, user=None, timeout=45):
        return raw(['exec', *(['--user', user] if user else []), client,
                    '/bin/sh', '-eu', '-c', script], check, timeout)

    def execute(script, user=None, check=True, target=None):
        assert target in {None, client}
        return raw(['exec', client, 'setpriv', '--no-new-privs', 'chroot',
                    '--userspec=' + (user or '0:0'), '/sles', '/bin/sh', '-eu', '-c', script], check)

    def popen(arguments, name):
        log = (output / (name + '.log')).open('w', encoding='utf-8')
        process = subprocess.Popen(engine + arguments, stdout=log, stderr=log)
        tasks.append((process, log))
        return process

    def spawn(script, name, target=None):
        assert target in {None, client}
        return popen(['exec', '--env', 'LD_BIND_NOW=1', client, 'setpriv', '--no-new-privs',
                      'chroot', '--userspec=1000:1000', '/sles', '/bin/sh', '-eu', '-c', script], name)

    try:
        record['driver_sha256'] = {name: hashlib.sha256((ROOT / 'scripts' / name).read_bytes()).hexdigest()
                                  for name in ['check-systemd-boundaries.py', 'systemd_runtime.py', 'nfs_runtime.py',
                                               'nfs_binding.py', 'nfs_both.py', 'nfs_bootstrap_state.py',
                                               'systemd/Containerfile', 'systemd/file-mover.service.in']}
        image = 'localhost/background-file-mover-systemd'
        record['image'] = json.loads(raw(['image', 'inspect', image]).stdout)[0]
        record['container_arguments'] = ['--systemd=always', '--cgroupns=private', '--privileged', '--network=none']
        client = raw(['create', *record['container_arguments'], image]).stdout.strip()
        record['container'] = client
        raw(['start', client])
        for _ in range(40):
            ready = host('systemctl show --property=Version --value', check=False)
            if ready.returncode == 0:
                break
            time.sleep(.25)
        else:
            raise RuntimeError('systemd manager did not start')
        record['manager_version'] = ready.stdout.strip()
        record['manager_os'] = host('cat /etc/os-release').stdout
        record['manager_packages'] = host('dpkg-query -W').stdout.splitlines()
        record['kernel'] = host('uname -r').stdout.strip()
        record['cgroups'] = host('cat /proc/1/cgroup; stat -f -c %t /sys/fs/cgroup').stdout.splitlines()
        assert record['cgroups'][-1] == '63677270' and host('cat /proc/1/comm').stdout.strip() == 'systemd'
        host('mount -t proc proc /sles/proc; mount --rbind /dev /sles/dev')
        record['service_os'] = execute('cat /etc/os-release').stdout
        record['service_glibc'] = execute('getconf GNU_LIBC_VERSION').stdout.strip()
        assert record['service_glibc'] == 'glibc 2.22' and 'VERSION_ID="12.5"' in record['service_os']
        assert execute('readlink /proc/self/ns/pid').stdout == host('readlink /proc/self/ns/pid').stdout
        hashes = {}
        for gate, report in zip(gates, reports):
            for profile, details in report['profiles'].items():
                artifact = next(a for a in details['artifacts'] if not a['test'])
                local = gate / artifact['name']
                assert hashlib.sha256(local.read_bytes()).hexdigest() == artifact['sha256']
                key = ('' if report['build_mode'] == 'production' else 'qualification-') + profile
                hashes[key] = artifact['sha256']
                run(['cp', str(local), client + ':/tmp/' + key])
                execute('chmod 755 /tmp/' + key)
                # v252 verify checks executable existence in the manager root.
                # Execution still uses RootDirectory; mapped libc is asserted.
                host(f'test ! -e /tmp/{key}; ln -s /sles/tmp/{key} /tmp/{key}')
        record['artifacts'] = hashes
        from nfs_runtime import run_runtime
        from systemd_runtime import exercise
        run_runtime(run, execute, spawn, lambda: None, None, output, client, hashes, record['cases'],
                    case_runner=lambda Case: exercise(Case, host, execute, spawn, popen, output, client, record))
        assert len(record['cases']) == 10 and all(c['passed'] for c in record['cases'])
        record['status'] = 'PASSED'
    except Exception as error:
        record.update(error=f'{type(error).__name__}: {error}', traceback=traceback.format_exc())
    finally:
        if client:
            try:
                record['final_journal'] = host('journalctl -b --no-pager -o short-monotonic', check=False).stdout
                result = raw(['rm', '--force', client], check=False, timeout=60)
                if result.returncode:
                    record['cleanup_errors'].append(result.stderr)
            except Exception as error:
                record['cleanup_errors'].append(str(error))
        for process, log in tasks:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
            log.close()
        if record['cleanup_errors']:
            record['status'] = 'FAILED'
        (output / 'report.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        print(f"{record['status']}: {output}", flush=True)
        if 'error' in record:
            print(record['error'], flush=True)
    return 0 if record['status'] == 'PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
