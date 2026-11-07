"""Two owned tmpfs-backed exports on the fixture server; no NAS durability claim."""


def prepare(run, execute, server, client, ip, options, extra_mounts, report):
    exports = ("/exports/death-source", "/exports/death-destination")
    mounts = ("/tmp/nfs-source", "/tmp/nfs-destination")
    for export, mount, fsid in zip(exports, mounts, (53, 54)):
        run(["exec", server, "/bin/sh", "-eu", "-c",
             f"mkdir {export}; mount -t tmpfs -o size=128m,nr_inodes=4096,mode=1777 tmpfs {export}; "
             f"exportfs -i -o rw,sync,no_subtree_check,no_root_squash,fsid={fsid} '*:{export}'"])
        execute("mkdir " + mount)
        run(["exec", client, "mount", "-i", "-t", "nfs4", "-o", options,
             ip + ":/" + export.rsplit("/", 1)[1], mount])
        extra_mounts.append((client, mount))
    report["mounts"] = execute("cat /proc/mounts").stdout.splitlines()
    report["mountinfo"] = execute("cat /proc/self/mountinfo").stdout.splitlines()
    report["server_mounts"] = run(["exec", server, "cat", "/proc/mounts"]).stdout.splitlines()
    report["server_devices"] = run(["exec", server, "stat", "-c", "%d", *exports]).stdout.splitlines()
    report["client_devices"] = execute("stat -c %d " + " ".join(mounts)).stdout.splitlines()
    report["client_filesystems"] = execute("stat -f -c %t " + " ".join(mounts)).stdout.splitlines()
    assert len(set(report["server_devices"])) == len(set(report["client_devices"])) == 2
    assert report["client_filesystems"] == ["6969", "6969"]
    mount_ids = []
    for export, mount in zip(exports, mounts):
        assert any(f" {export} tmpfs " in m and "size=131072k" in m and "nr_inodes=4096" in m
                   for m in report["server_mounts"])
        assert any(f" {mount} nfs4 " in m and "vers=4.1" in m and "hard" in m
                   and ip + ":/" + export.rsplit("/", 1)[1] in m for m in report["mounts"])
        records = [m.split() for m in report["mountinfo"] if m.split()[4] == mount]
        assert len(records) == 1
        mount_ids.append(records[0][0])
    assert len(set(mount_ids)) == 2
    report["client_mount_ids"] = mount_ids
    execute("umask 077; printf 'cross-export probe' >/tmp/nfs-source/cross-export-probe", "1000:1000")
    before = execute("stat -c '%d:%i:%s' /tmp/nfs-source/cross-export-probe; sha256sum /tmp/nfs-source/cross-export-probe", "1000:1000").stdout
    refused = execute("LC_ALL=C ln /tmp/nfs-source/cross-export-probe /tmp/nfs-destination/forbidden-link", "1000:1000", check=False)
    assert refused.returncode != 0 and "Invalid cross-device link" in refused.stderr, refused.stderr
    execute("test ! -e /tmp/nfs-destination/forbidden-link", "1000:1000")
    after = execute("stat -c '%d:%i:%s' /tmp/nfs-source/cross-export-probe; sha256sum /tmp/nfs-source/cross-export-probe", "1000:1000").stdout
    assert before == after
    report.update(passed=True, cross_export_link={"exit_code": refused.returncode, "stderr": refused.stderr,
                  "source_preserved": True, "destination_absent": True},
                  scope="Two distinct tmpfs-backed exports/mounts on one controlled NFSv4.1 server; joint outage only. No independent NAS failure, persistent-disk or power-loss evidence.")
