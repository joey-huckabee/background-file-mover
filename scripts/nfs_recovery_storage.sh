#!/bin/sh
# Two bounded filesystem identities retained independently of the NFS server.
set -eu
mkdir -p /exports/profile-source /exports/profile-destination
# Podman's local driver mounts the two bounded tmpfs volumes. This container
# holds their references while the separate NFS backend restarts.
printf 'NFS_STORAGE_READY\n'
exec sleep infinity
