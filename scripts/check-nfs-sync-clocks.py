#!/usr/bin/env python3
"""Read-only clock-namespace qualification alongside a live --sync-observe run."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('worker_run')
args = parser.parse_args()
folder = Path(args.worker_run).resolve()
root = Path(__file__).resolve().parents[1]
assert folder.is_relative_to(root / 'rust/validation') and folder.is_dir()
assert re.fullmatch(r'nfs-\d{8}T\d{6}Z-[0-9a-f]{8}', folder.name)
engine = ['podman', '--connection', 'podman-machine-default-root']
network = 'bfm-' + folder.name.lower()
output = folder / 'sync-clock-report.json'
rows, client = {}, None
result = dict(status='OBSERVING', run_id=folder.name, actors=[],
    driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    scope='Actual /proc/self/ns/time in all four external observers and owned relay/client containers')
try:
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        listed = subprocess.run(engine + ['ps', '-a', '-q', '--no-trunc'],
            capture_output=True, text=True, timeout=45, check=True)
        ids = listed.stdout.split()
        objects = []
        if ids:
            inspected = subprocess.run(engine + ['inspect', *ids], capture_output=True,
                text=True, timeout=45)
            # Teardown may remove one listed container. Keep valid remaining
            # objects, or try again; never infer a namespace from a missing PID.
            try:
                objects = json.loads(inspected.stdout)
            except json.JSONDecodeError:
                objects = []
        for obj in objects:
            if network in obj['NetworkSettings']['Networks'] and 'sles12sp5@' in obj['Config']['Image']:
                client = obj['Id']
        for obj in objects:
            own = network in obj['NetworkSettings']['Networks']
            observer = client is not None and obj['HostConfig']['PidMode'] == 'container:' + client
            if not (own or observer) or obj['Id'] in rows or not obj['State']['Running']:
                continue
            value = subprocess.run(engine + ['exec', obj['Id'], 'readlink', '/proc/self/ns/time'],
                capture_output=True, text=True, timeout=20)
            if value.returncode:
                continue  # An observer may finish before exec; not clock proof.
            namespace = value.stdout.strip()
            assert namespace.startswith('time:[')
            rows[obj['Id']] = dict(container=obj['Id'], entrypoint=obj['Config']['Entrypoint'],
                pid_mode=obj['HostConfig']['PidMode'], time_namespace=namespace, observer=observer)
            assert len({r['time_namespace'] for r in rows.values()}) == 1, 'clock namespace mismatch'
        result['actors'] = list(rows.values())
        output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        if sum(r['observer'] for r in rows.values()) == 4:
            result['status'] = 'PASSED'
            break
        if (folder / 'report.json').exists():
            break
        time.sleep(1)
    if result['status'] != 'PASSED':
        result.update(status='FAILED', error='Incomplete live clock observations; start alongside the worker run before traces begin')
except Exception as error:
    result.update(status='FAILED', error=str(error), actors=list(rows.values()))
finally:
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(result['status'] + ': clock namespace audit, ' + str(len(rows)) + ' actors; '
      + str(sum(r['observer'] for r in rows.values())) + ' actual observers', flush=True)
raise SystemExit(0 if result['status'] == 'PASSED' else 1)
