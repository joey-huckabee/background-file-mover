"""Independently stop two owned NFS servers; no physical NAS/power-loss claim."""
import hashlib
import json
import time


class Endpoints:
    def __init__(self, run, execute, server, client, ip, options, network, image,
                 containers, volumes, servers, extra_mounts, report, destination_relay=None):
        self.run, self.execute, self.client = run, execute, client
        self.report = report
        self.counter = 0
        volume = network + "-destination"
        run(["volume", "create", volume])
        volumes.append(volume)
        destination = run(["create", "--privileged", "--network", network,
                           "--volume", volume + ":/exports", image]).stdout.strip()
        containers.append(destination)
        run(["start", destination])
        for _ in range(40):
            if "NFS_READY" in run(["logs", destination]).stdout:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("independent destination NFS server not ready")
        servers.append(destination)
        destination_ip = json.loads(run(["inspect", destination]).stdout)[0]["NetworkSettings"]["Networks"][network]["IPAddress"]
        assert destination_ip != ip
        self.relay = destination_relay(destination_ip) if destination_relay else None
        destination_mount_ip = self.relay.address if self.relay else destination_ip
        self.servers = {"source": server, "destination": destination}
        self.mounts = {"source": "/tmp/nfs-source", "destination": "/tmp/nfs-destination"}
        report["servers"] = {}
        for role, address, fsid in (("source", ip, 55), ("destination", destination_mount_ip, 56)):
            target, mount = self.servers[role], self.mounts[role]
            export = "/exports/death-" + role
            run(["exec", target, "/bin/sh", "-eu", "-c",
                 f"mkdir {export}; mount -t tmpfs -o size=128m,nr_inodes=4096,mode=1777 tmpfs {export}; "
                 f"exportfs -i -o rw,sync,no_subtree_check,no_root_squash,fsid={fsid} '*:{export}'"])
            execute("mkdir " + mount)
            mount_options = options.replace("addr=" + ip + ",", "addr=" + address + ",")
            run(["exec", client, "mount", "-i", "-t", "nfs4", "-o", mount_options,
                 address + ":/death-" + role, mount])
            extra_mounts.append((client, mount))
            report["servers"][role] = dict(container=target, ip=address, export=export, mount=mount,
                network_namespace=run(["exec", target, "readlink", "/proc/self/ns/net"]).stdout.strip(),
                filesystem_device=run(["exec", target, "stat", "-c", "%d", export]).stdout.strip(),
                server_mounts=run(["exec", target, "cat", "/proc/mounts"]).stdout.splitlines())
            if role == "destination" and self.relay:
                report["servers"][role]["backend_ip"] = destination_ip
                report["reply_relay"] = self.relay.evidence
            assert any(f" {export} tmpfs " in m and "size=131072k" in m and "nr_inodes=4096" in m
                       for m in report["servers"][role]["server_mounts"])
            self.healthy(role)
        assert len({v["network_namespace"] for v in report["servers"].values()}) == 2
        assert len({v["filesystem_device"] for v in report["servers"].values()}) == 2
        report["mounts"] = execute("cat /proc/mounts").stdout.splitlines()
        report["mountinfo"] = execute("cat /proc/self/mountinfo").stdout.splitlines()
        report["client_devices"] = execute("stat -c %d /tmp/nfs-source /tmp/nfs-destination").stdout.splitlines()
        report["client_filesystems"] = execute("stat -f -c %t /tmp/nfs-source /tmp/nfs-destination").stdout.splitlines()
        assert len(set(report["client_devices"])) == 2 and report["client_filesystems"] == ["6969", "6969"]
        ids = []
        for value in report["servers"].values():
            assert any(value["ip"] + ":/death-" in m and f" {value['mount']} nfs4 " in m
                       and "hard" in m and "vers=4.1" in m for m in report["mounts"])
            rows = [m.split() for m in report["mountinfo"] if m.split()[4] == value["mount"]]
            assert len(rows) == 1
            ids.append(rows[0][0])
        assert len(set(ids)) == 2
        report["client_mount_ids"] = ids
        report["passed"] = True
        report["scope"] = "Two controlled NFSv4.1 server containers/net namespaces/IPs and tmpfs exports on one modern kernel; independent NFSD thread outages, not physical NAS failures or reboot/power durability."

    def healthy(self, role):
        self.counter += 1
        path = self.mounts[role] + "/healthy-" + str(self.counter)
        began = time.monotonic()
        response = self.execute(f"umask 077; (set -C; printf 'healthy endpoint' >{path}); "
                                f"stat -c '%d:%i:%s' {path}; sha256sum {path}", "1000:1000")
        elapsed = time.monotonic() - began
        assert elapsed < 5
        lines = response.stdout.splitlines()
        assert lines[0].split(":")[-1] == "16" and lines[1].split()[0] == hashlib.sha256(b"healthy endpoint").hexdigest()
        return dict(role=role, elapsed_seconds=round(elapsed, 3), fresh_write_read_metadata=lines)

    def stop(self, role):
        self.run(["exec", self.servers[role], "rpc.nfsd", "0"])
        threads = {name: self.run(["exec", target, "cat", "/proc/fs/nfsd/threads"]).stdout.strip()
                   for name, target in self.servers.items()}
        other = "destination" if role == "source" else "source"
        assert threads[role] == "0" and threads[other] == "2", threads
        return dict(failed_endpoint=role, nfsd_threads=threads, healthy=self.healthy(other))

    def during(self, role):
        return self.healthy("destination" if role == "source" else "source")
