"""Provision only fixed, disposable fixture markers; never service enrollment."""
import json
from nfs_mount_profile import parse, covering

# Only newly provisioned disposable fixtures. Never refreshed at service restart.
_PROVISIONED_PROFILES = {}


def binding_for(label, nfs, role="source"):
    result = {"version": 3, "coordinator_id": "fixture-owner", "root_id": label,
            "endpoint_id": "fixture-nfs" if nfs else "fixture-local", "marker_id": label + "-marker",
            "filesystem": "nfs" if nfs else "local", "role": role}
    if nfs and (label, role) in _PROVISIONED_PROFILES:
        result['nfs_mount'] = dict(_PROVISIONED_PROFILES[(label, role)])
    return result


def provision(run, execute, output, client, source, binding):
    # The root/namespace must already be provisioned by the owning fixture.
    if binding['filesystem'] == 'nfs':
        inventory = execute('cat /proc/self/mountinfo', '1000:1000', target=client).stdout
        mount = covering(parse(inventory), source)
        assert mount['filesystem'] in ('nfs', 'nfs4')
        profile = dict(profile='NMP-41N' if 'noac' in mount['super'] else 'NMP-41B',
                       mountpoint=mount['point'], source=mount['source'], addr=mount['super']['addr'])
        binding['nfs_mount'] = profile
        _PROVISIONED_PROFILES[(binding['root_id'], binding['role'])] = dict(profile)
    label = binding["marker_id"]
    assert label and all(c.isalnum() or c in "-_" for c in label)
    local = output / (label + ".json")
    local.write_text(json.dumps(binding))
    remote = "/tmp/" + label + ".json"
    run(["cp", str(local), client + ":" + remote])
    marker = binding["role"] + "-binding.json"
    execute(f"umask 077; test ! -e {source}/.file-mover/coordinator.lock; "
            f"(set -C; : >{source}/.file-mover/coordinator.lock); chmod 600 {source}/.file-mover/coordinator.lock; "
            f"test ! -e {source}/.file-mover/{marker}; "
            f"cat {remote} >{source}/.file-mover/{marker}; chmod 600 {source}/.file-mover/{marker}",
            "1000:1000", target=client)
