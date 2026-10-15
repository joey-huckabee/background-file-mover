"""Provision only fixed, disposable fixture markers; never service enrollment."""
import json


def binding_for(label, nfs):
    return {"version": 1, "coordinator_id": "fixture-owner", "root_id": label,
            "endpoint_id": "fixture-nfs" if nfs else "fixture-local", "marker_id": label + "-marker",
            "filesystem": "nfs" if nfs else "local", "role": "source"}


def provision(run, execute, output, client, source, binding):
    # The root/namespace must already be provisioned by the owning fixture.
    label = binding["marker_id"]
    assert label and all(c.isalnum() or c in "-_" for c in label)
    local = output / (label + ".json")
    local.write_text(json.dumps(binding))
    remote = "/tmp/" + label + ".json"
    run(["cp", str(local), client + ":" + remote])
    execute(f"umask 077; test ! -e {source}/.file-mover/source-binding.json; "
            f"cat {remote} >{source}/.file-mover/source-binding.json; chmod 600 {source}/.file-mover/source-binding.json",
            "1000:1000", target=client)
