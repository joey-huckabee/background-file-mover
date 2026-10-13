#!/bin/sh
# Controlled fixture only. No ports published; /exports is a disposable volume.
set -eu
mkdir -p /exports /proc/fs/nfsd /run/rpcbind
chmod 1777 /exports
mount -t nfsd nfsd /proc/fs/nfsd
printf '/exports *(rw,sync,no_subtree_check,no_root_squash,fsid=0)\n' > /etc/exports
rpcbind
exportfs -rav
rpc.mountd
rpc.idmapd -S
rpc.nfsd -G 10 -L 10 -V 4 -p 2049 2
# Fresh isolated server has no old clients whose locks must be reclaimed.
# End the default 90-second recovery grace before allowing the probe to open files.
sleep 11
exportfs -v
printf 'NFS_READY\n'
exec sleep infinity
