#!/usr/bin/env python3
"""Bounded private-container 228 preflight; never a lifecycle pass declaration."""
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
CONFIG = json.loads((ROOT / 'scripts/rust-platform.json').read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('gate', type=Path)
    parser.add_argument('--qualification-gate', type=Path, required=True)
    parser.add_argument('--connection', default='podman-machine-default-root')
    args = parser.parse_args()
    gates = [args.gate.resolve(), args.qualification_gate.resolve()]
    inputs = {p.relative_to(ROOT / 'rust').as_posix(): p.read_bytes()
              for child in (ROOT / 'rust').iterdir() if child.name not in {'target', 'validation'}
              for p in (child.rglob('*') if child.is_dir() else [child]) if p.is_file()}
    reports = []
    for gate, mode in zip(gates, ['production', 'nfs-qualification']):
        r = json.loads((gate / 'report.json').read_text(encoding='utf-8'))
        assert r['status'] == 'PASSED' and r['build_mode'] == mode and r['config'] == CONFIG
        archive_path = gate / 'source.tar.gz'
        assert hashlib.sha256(archive_path.read_bytes()).hexdigest() == r['source_sha256']
        with tarfile.open(archive_path) as archive:
            assert {m.name for m in archive.getmembers() if m.isfile()} == set(inputs)
            for m in archive.getmembers():
                if m.isfile():
                    assert archive.extractfile(m).read() == inputs[m.name]
        reports.append(r)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    output = ROOT / 'rust/validation' / ('systemd228-' + stamp)
    output.mkdir()
    record = dict(status='FAILED', run_id=output.name, gate=gates[0].name,
                  qualification_gate=gates[1].name, cleanup_errors=[],
                  native_sles_rpm_qualified=False, lifecycle_qualified=False,
                  scope='Leap 42.3 equivalent manager; pinned SLES service root; private cgroup v2 preflight only',
                  lifecycle_cases=[dict(production=mode, profile=p, kind=k, status='NOT_RUN')
                                   for mode in [True, False] for p in ['debug', 'release']
                                   for k in (['basic'] if mode else ['basic', 'incomplete', 'manual-orphan', 'managed-crash'])])
    engine = ['podman', '--connection', args.connection]
    containers = []

    def run(arguments, check=True, timeout=25):
        result = subprocess.run(engine + arguments, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=timeout)
        if check and result.returncode:
            raise RuntimeError(f'{arguments}: {result.stdout}{result.stderr}')
        return result

    def reply(result):
        return dict(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)

    def execute(client, script, check=True):
        return run(['exec', client, '/bin/sh', '-eu', '-c', script], check)

    def create(arguments):
        client = run(['create', *arguments]).stdout.strip()
        containers.append(client)
        run(['start', client])
        return client

    try:
        drivers = ['check-systemd228-preflight.py', 'systemd/Containerfile.228',
                   'systemd/file-mover-228.service.in', 'systemd/file-mover.service.in']
        record['driver_sha256'] = {name: hashlib.sha256((ROOT / 'scripts' / name).read_bytes()).hexdigest()
                                  for name in drivers}
        image = 'localhost/background-file-mover-systemd228'
        record['image'] = json.loads(run(['image', 'inspect', image]).stdout)[0]
        client = create(['--network=none', '--cap-drop=all', '--cap-add=SYS_CHROOT', '--cgroupns=private', image, '/bin/sleep', 'infinity'])
        record['manager_version'] = execute(client, '/usr/lib/systemd/systemd --version').stdout
        assert record['manager_version'].startswith('systemd 228\n')
        record['manager_os'] = execute(client, 'cat /etc/os-release').stdout
        record['manager_packages'] = execute(client, 'rpm -qa | sort').stdout.splitlines()
        record['manager_glibc'] = execute(client, 'getconf GNU_LIBC_VERSION').stdout.strip()
        record['manager_binary_sha256'] = execute(client, 'sha256sum /usr/lib/systemd/systemd').stdout.split()[0]
        inventory = execute(client, '/usr/lib/systemd/systemd --dump-configuration-items').stdout
        record['compiled_directive_inventory'] = inventory
        supported = set()
        section = ''
        for line in inventory.splitlines():
            if line.startswith('[') and line.endswith(']'):
                section = line[1:-1]
            elif '=' in line:
                supported.add((section, line.split('=', 1)[0].strip()))
        record['service_os'] = execute(client, 'chroot /sles /bin/cat /etc/os-release').stdout
        record['service_glibc'] = execute(client, 'chroot /sles /usr/bin/getconf GNU_LIBC_VERSION').stdout.strip()
        assert 'VERSION_ID="42.3"' in record['manager_os'] and 'VERSION_ID="12.5"' in record['service_os']
        assert record['manager_glibc'] == record['service_glibc'] == 'glibc 2.22'
        record['kernel'] = execute(client, 'uname -r').stdout.strip()
        record['private_cgroup_layout'] = execute(client, 'cat /proc/self/cgroup; stat -f -c %t /sys/fs/cgroup').stdout
        record['artifacts'] = {}
        for gate, r in zip(gates, reports):
            for profile, details in r['profiles'].items():
                a = next(a for a in details['artifacts'] if not a['test'])
                local = gate / a['name']
                assert hashlib.sha256(local.read_bytes()).hexdigest() == a['sha256']
                key = ('' if r['build_mode'] == 'production' else 'qualification-') + profile
                run(['cp', str(local), client + ':/sles/tmp/' + key])
                execute(client, f'chmod 755 /sles/tmp/{key}; ln -s /sles/tmp/{key} /tmp/{key}')
                assert execute(client, f'sha256sum /sles/tmp/{key}').stdout.split()[0] == a['sha256']
                record['artifacts'][key] = a['sha256']
        record['unit_checks'] = []
        for kind, filename in [('legacy_candidate', 'file-mover-228.service.in'), ('modern_negative_control', 'file-mover.service.in')]:
            template = (ROOT / 'scripts/systemd' / filename).read_text(encoding='utf-8')
            unit = 'fm-228-' + kind.replace('_', '-') + '.service'
            text = template.format(binary='/tmp/release', config='/tmp/fixture-config.json',
                                   envfile='/run/fm-228.env', pregate='true', restart='on-failure', stop_timeout=75)
            local = output / unit
            local.write_text(text, encoding='utf-8')
            run(['cp', str(local), client + ':/etc/systemd/system/' + unit])
            execute(client, ': >/run/fm-228.env')
            result = execute(client, f'systemd-analyze verify /etc/systemd/system/{unit}', check=False)
            unsupported = []
            section = ''
            for line in text.splitlines():
                if line.startswith('[') and line.endswith(']'):
                    section = line[1:-1]
                elif '=' in line and not line.startswith('#'):
                    directive = line.split('=', 1)[0]
                    if (section, directive) not in supported:
                        unsupported.append(section + '.' + directive)
            if kind == 'legacy_candidate':
                assert not unsupported, unsupported
            else:
                assert 'Unit.StartLimitIntervalSec' in unsupported, unsupported
            record['unit_checks'].append(dict(kind=kind, text=text, unsupported_directives=unsupported, **reply(result)))
        record['boot_arguments'] = ['--systemd=always', '--cgroupns=private', '--privileged', '--network=none']
        boot = create([*record['boot_arguments'], image])
        record['boot_container'] = boot
        probes = []
        began = time.monotonic()
        for _ in range(6):
            result = run(['exec', boot, 'systemctl', 'show', '-p', 'Version'], check=False, timeout=8)
            probes.append(reply(result))
            if result.returncode == 0:
                break
            if not json.loads(run(['inspect', boot]).stdout)[0]['State']['Running']:
                break
            time.sleep(.25)
        record['manager_probes'] = probes
        record['startup_probe_seconds'] = round(time.monotonic() - began, 3)
        record['manager_ready'] = probes[-1]['exit_code'] == 0
        record['boot_logs'] = reply(run(['logs', boot], check=False))
        record['boot_state'] = json.loads(run(['inspect', boot]).stdout)[0]['State']
        if record['boot_state']['Running']:
            record['boot_layout'] = reply(execute(boot, 'cat /proc/1/comm; cat /proc/1/cgroup; stat -f -c %t /sys/fs/cgroup', check=False))
        record['status'] = 'PREFLIGHT_READY' if record['manager_ready'] else 'BLOCKED'
        record['blocked_reason'] = ('Exact SLES systemd RPM revision unavailable; equivalent manager startup alone is not lifecycle qualification.'
                                    if record['manager_ready'] else
                                    'The unmodified equivalent 228 manager did not expose its control bus in the fully private cgroup-v2 container; lifecycle matrix not run.')
    except Exception as error:
        record.update(error=f'{type(error).__name__}: {error}', traceback=traceback.format_exc())
    finally:
        for client in reversed(containers):
            try:
                result = run(['rm', '--force', client], check=False, timeout=45)
                if result.returncode:
                    record['cleanup_errors'].append(result.stderr)
            except Exception as error:
                record['cleanup_errors'].append(str(error))
        if record['cleanup_errors']:
            record['status'] = 'FAILED'
        (output / 'report.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        print(f"{record['status']}: {output}", flush=True)
        if record.get('error'):
            print(record['error'], flush=True)
    return 0 if record['status'] == 'PREFLIGHT_READY' else 2 if record['status'] == 'BLOCKED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
