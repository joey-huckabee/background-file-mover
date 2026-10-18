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
    parser.add_argument('--manager', choices=['252', '228'], default='252')
    parser.add_argument('--allow-host-cgroup-bootstrap', action='store_true')
    args = parser.parse_args()
    legacy = args.manager == '228'
    if legacy and not args.allow_host_cgroup_bootstrap:
        parser.error('228 bootstrap requires explicit approval and --allow-host-cgroup-bootstrap')
    if args.allow_host_cgroup_bootstrap and not legacy:
        parser.error('the broader bootstrap is available only for --manager 228')
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
    record['manager_profile'] = args.manager
    record['broader_bootstrap_acknowledged'] = args.allow_host_cgroup_bootstrap
    if legacy:
        record['scope'] = 'Approved broader bootstrap; Leap 42.3 systemd 228 equivalent; pinned SLES service root; local payload/state only; no exact SLES RPM, native old kernel, hard-NFS/systemd, reboot, persistence or host account-policy qualification'
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

    def prefix(user=None):
        if legacy:
            base = ['exec', client, '/usr/local/libexec/enter-228.sh']
            if user:
                uid, gid = user.split(':')
                base += ['setpriv', '--no-new-privs', '--reuid=' + uid,
                         '--regid=' + gid, '--clear-groups']
            return base
        return ['exec', *(['--user', user] if user else []), client]

    def host(script, check=True, user=None, timeout=45):
        return raw(prefix(user) + ['/bin/sh', '-eu', '-c', script], check, timeout)

    def execute(script, user=None, check=True, target=None):
        assert target in {None, client}
        return raw(prefix() + ['setpriv', '--no-new-privs', 'chroot',
                    '--userspec=' + (user or '0:0'), '/sles', '/bin/sh', '-eu', '-c', script], check)

    def popen(arguments, name):
        if legacy and arguments[:2] == ['exec', client] and arguments[2] != '/usr/local/libexec/enter-228.sh':
            arguments = prefix() + arguments[2:]
        log = (output / (name + '.log')).open('w', encoding='utf-8')
        process = subprocess.Popen(engine + arguments, stdout=log, stderr=log)
        tasks.append((process, log))
        return process

    def spawn(script, name, target=None):
        assert target in {None, client}
        if legacy:
            return popen(prefix() + ['env', 'LD_BIND_NOW=1', 'setpriv', '--no-new-privs',
                         'chroot', '--userspec=1000:1000', '/sles', '/bin/sh', '-eu', '-c', script], name)
        return popen(['exec', '--env', 'LD_BIND_NOW=1', client, 'setpriv', '--no-new-privs',
                      'chroot', '--userspec=1000:1000', '/sles', '/bin/sh', '-eu', '-c', script], name)

    try:
        record['driver_sha256'] = {name: hashlib.sha256((ROOT / 'scripts' / name).read_bytes()).hexdigest()
                                  for name in ['check-systemd-boundaries.py', 'systemd_runtime.py', 'nfs_runtime.py',
                                               'nfs_binding.py', 'nfs_both.py', 'nfs_bootstrap_state.py',
                                               'systemd/Containerfile', 'systemd/file-mover.service.in']}
        if legacy:
            for name in ['systemd/Containerfile.228', 'systemd/Containerfile.228-approved',
                         'systemd/boot-228-approved.sh', 'systemd/boot-228-inner.sh',
                         'systemd/enter-228.sh', 'systemd/cleanup-228.sh', 'systemd/file-mover-228.service.in']:
                record['driver_sha256'][name] = hashlib.sha256((ROOT / 'scripts' / name).read_bytes()).hexdigest()
        image = 'localhost/background-file-mover-systemd228-approved' if legacy else 'localhost/background-file-mover-systemd'
        record['image'] = json.loads(raw(['image', 'inspect', image]).stdout)[0]
        if legacy:
            base = json.loads(raw(['image', 'inspect', 'localhost/background-file-mover-systemd228']).stdout)[0]
            record['fixture_base_image'] = base
            layers = base['RootFS']['Layers']
            assert record['image']['RootFS']['Layers'][:len(layers)] == layers
            assert record['image']['Config']['Cmd'] == ['/usr/local/libexec/boot-228-approved.sh']
            before = raw(['run', '--rm', '--network=none', '--cap-drop=all', '--cgroupns=host',
                          'localhost/background-file-mover-systemd228', '/bin/cat', '/proc/self/cgroup'])
            record['pre_bootstrap_cgroups'] = before.stdout
            if 'name=systemd' in before.stdout:
                raise RuntimeError('Refusing existing legacy hierarchy before creating a fixture')
        record['container_arguments'] = ['--systemd=always', '--cgroupns=' + ('host' if legacy else 'private'), '--privileged', '--network=none']
        owner = uuid.uuid4().hex if legacy else None
        if legacy:
            record['cgroup_owner_nonce'] = owner
        client = raw(['create', *record['container_arguments'], *(['--env=FILE_MOVER_CGROUP_OWNER=' + owner] if legacy else []), image]).stdout.strip()
        record['container'] = client
        raw(['start', client])
        for _ in range(40):
            ready = host('systemctl show --property=Version' + ('' if legacy else ' --value'), check=False)
            if ready.returncode == 0:
                break
            time.sleep(.25)
        else:
            raise RuntimeError('systemd manager did not start')
        record['manager_version'] = ready.stdout.strip().removeprefix('Version=')
        assert record['manager_version'].startswith('228' if legacy else '252')
        record['manager_os'] = host('cat /etc/os-release').stdout
        record['manager_packages'] = host('rpm -qa | sort' if legacy else 'dpkg-query -W').stdout.splitlines()
        record['manager_glibc'] = host('getconf GNU_LIBC_VERSION').stdout.strip()
        if legacy:
            assert 'VERSION_ID="42.3"' in record['manager_os']
            assert 'systemd-228-71.1.x86_64' in record['manager_packages']
            record['service_account'] = host('getent passwd mover; getent group mover; id mover').stdout
            assert host('id -u mover; id -g mover').stdout.splitlines() == ['1000', '1000']
        record['kernel'] = host('uname -r').stdout.strip()
        record['cgroups'] = host('cat /proc/1/cgroup; stat -f -c %t /sys/fs/cgroup' + (' /sys/fs/cgroup/systemd' if legacy else '')).stdout.splitlines()
        assert record['cgroups'][-1] == ('27e0eb' if legacy else '63677270')
        assert host('cat /proc/1/comm').stdout.strip() == 'systemd'
        if legacy:
            outer = host('cat /run/fm-outer-cgroup-namespace').stdout.strip()
            inner = host('readlink /proc/1/ns/cgroup').stdout.strip()
            helper = host('readlink /proc/self/ns/cgroup').stdout.strip()
            assert inner == helper and inner != outer
            assert host('test ! -d /sys/fs/cgroup/systemd/$(cat /run/fm-owned-cgroup-name); test ! -e /run/fm-cgroup-bootstrap/cgroup.procs', check=False).returncode == 0
            assert record['manager_glibc'] == 'glibc 2.22'
            record['cgroup_namespaces'] = dict(bootstrap_outer=outer, manager=inner, helper=helper)
            record['namespace_root_view'] = host('cat /proc/self/cgroup').stdout
            record['executed_helper_sha256'] = {}
            for helper_name in ['boot-228-approved.sh', 'boot-228-inner.sh', 'enter-228.sh', 'cleanup-228.sh']:
                digest = host('sha256sum /usr/local/libexec/' + helper_name).stdout.split()[0]
                assert digest == record['driver_sha256']['systemd/' + helper_name]
                record['executed_helper_sha256'][helper_name] = digest
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
                record['final_journal'] = host('journalctl -b --no-pager -o short-monotonic', check=False, timeout=15).stdout
            except Exception as error:
                record['journal_capture_error'] = str(error)
            try:
                logs = raw(['logs', client], check=False, timeout=10)
                record['boot_logs'] = logs.stdout + logs.stderr
                if legacy:
                    record['bootstrap_ownership_attested'] = ('FILE_MOVER_OWNED_CGROUP=file-mover-owned-' + owner) in record['boot_logs'].splitlines()
            except Exception as error:
                record['boot_log_capture_error'] = str(error)
            try:
                result = raw(['rm', '--force', client], check=False, timeout=60)
                if result.returncode:
                    record['cleanup_errors'].append(result.stderr)
            except Exception as error:
                record['cleanup_errors'].append(str(error))
            if legacy:
                try:
                    if record.get('bootstrap_ownership_attested'):
                        cleanup = raw(['run', '--rm', '--network=none', '--privileged', '--cgroupns=host',
                                       image, '/usr/local/libexec/cleanup-228.sh', record['cgroup_owner_nonce']], check=False)
                        record['owned_cgroup_cleanup'] = dict(exit_code=cleanup.returncode, stdout=cleanup.stdout, stderr=cleanup.stderr)
                        if cleanup.returncode:
                            record['cleanup_errors'].append(cleanup.stderr or cleanup.stdout)
                    else:
                        record['owned_cgroup_cleanup'] = dict(exit_code=None, stdout='Not attached: bootstrap did not attest creation of its owned subtree', stderr='')
                    probe = raw(['run', '--rm', '--network=none', '--cap-drop=all', '--cgroupns=host',
                                 'localhost/background-file-mover-systemd228', '/bin/cat', '/proc/self/cgroup'])
                    record['post_cleanup_cgroups'] = probe.stdout
                    if 'name=systemd' in probe.stdout:
                        record['cleanup_errors'].append('Legacy hierarchy remains after fixture cleanup')
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
