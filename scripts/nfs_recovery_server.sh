#!/bin/sh
# Owned container fixture; preserved volume, no host or NAS configuration.
set -eu
mkdir -p /exports/profile-source /exports/profile-destination /proc/fs/nfsd /run/rpcbind
chmod 1777 /exports /exports/profile-source /exports/profile-destination
mount -t nfsd nfsd /proc/fs/nfsd
printf '/exports *(rw,sync,no_subtree_check,root_squash,fsid=0)\n/exports/profile-source *(rw,sync,no_subtree_check,root_squash,fsid=68)\n/exports/profile-destination *(rw,sync,no_subtree_check,root_squash,fsid=69)\n' >/etc/exports
rpcbind
exportfs -rav
rpc.mountd
rpc.idmapd -S
rpc.nfsd -G 10 -L 10 -V 4 -p 2049 2
sleep 11
printf 'NFS_RECOVERY_READY\n'
exec sleep infinity
