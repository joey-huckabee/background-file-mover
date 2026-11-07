FROM docker.io/library/debian@sha256:a4672c0cb26fbdde88e38fa2dfb6c681942306680e41e4378b28770b6e79ee91
RUN printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d && chmod 755 /usr/sbin/policy-rc.d && apt-get update && apt-get install -y --no-install-recommends nfs-kernel-server rpcbind && rm -rf /var/lib/apt/lists/*
COPY nfs-server.sh /usr/local/bin/e2-nfs-server
ENTRYPOINT ["/bin/sh", "/usr/local/bin/e2-nfs-server"]
