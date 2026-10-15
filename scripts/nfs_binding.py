"""Provision only fixed, disposable fixture markers; never service enrollment."""
import json


def binding_for(label, nfs, role="source"):
    return {"version": 3, "coordinator_id": "fixture-owner", "root_id": label,
            "endpoint_id": "fixture-nfs" if nfs else "fixture-local", "marker_id": label + "-marker",
            "filesystem": "nfs" if nfs else "local", "role": role}


def provision(run, execute, output, client, source, binding):
    # The root/namespace must already be provisioned by the owning fixture.
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
