#!/usr/bin/env python3
"""Read both Podman inventories after an owned lab and retain cleanup evidence."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess


def inventory(extra):
    def output(*args):
        return subprocess.check_output(['podman', *extra, *args], text=True, encoding='utf-8', timeout=45)
    volumes = output('volume', 'ls', '--format', '{{.Name}}').splitlines()
    metadata = json.loads(output('volume', 'inspect', *volumes)) if volumes else []
    return dict(containers=output('ps', '-a', '--format', '{{.ID}}').splitlines(),
                volumes=volumes, networks=output('network', 'ls', '--format', '{{.Name}}').splitlines(),
                volume_metadata=[{k:v.get(k) for k in ('Name','CreatedAt','Anonymous','Labels')} for v in metadata])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('live', type=Path)
    args = parser.parse_args()
    assert args.live.is_dir(), 'live output directory must already exist'
    result = dict(captured_at_utc=datetime.now(timezone.utc).isoformat(),
                  default=inventory([]), rootful=inventory(['--connection','podman-machine-default-root']))
    assert not result['default']['containers'] and not result['rootful']['containers'], result
    assert set(result['rootful']['volumes']) == {'file-mover-rustup-1-99','file-mover-cargo-registry'}, result
    assert result['rootful']['networks'] == ['podman'], result
    path = args.live/'post-run-inventory.json'
    path.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(path)


if __name__ == '__main__':
    main()
