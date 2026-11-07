"""Owned memory filesystems retained across backend restart; never disk/power proof."""
import json
import time
from nfs_mount_profile import covering, parse


def create_storage(run,root,volume,image,containers,report,role_volumes):
    for role in ('source','destination'):
        name=volume+'-'+role
        run(['volume','create','--opt','type=tmpfs','--opt','device=tmpfs',
             '--opt','o=size=64m,nr_inodes=4096,mode=1777',name])
        role_volumes.append(name)
    report['storage_volumes']=[json.loads(run(['volume','inspect',name]).stdout)[0] for name in role_volumes]
    keeper=run(['create','--privileged','--network','none','--volume',volume+':/exports',
                *role_binds(role_volumes,'/exports'),
                '--entrypoint','/bin/sh',image,'/tmp/nfs_recovery_storage.sh']).stdout.strip()
    containers.append(keeper)
    run(['cp',str(root/'scripts/nfs_recovery_storage.sh'),keeper+':/tmp/nfs_recovery_storage.sh'])
    run(['start',keeper])
    for _ in range(30):
        if 'NFS_STORAGE_READY' in run(['logs',keeper]).stdout:break
        time.sleep(.1)
    else:raise AssertionError('storage keeper did not become ready')
    observed=storage_state(run,keeper)
    assert observed['devices']['source']!=observed['devices']['destination']
    report['storage']=dict(keeper=keeper,before=observed,bounded_bytes_per_role=64*1048576,
                           bounded_inodes_per_role=4096,persistent_medium=False)
    return keeper


def storage_state(run,keeper):
    info=json.loads(run(['inspect',keeper]).stdout)[0]
    assert info['State']['Running'] and info['State']['Pid']>0
    inventory=run(['exec',keeper,'cat','/proc/self/mountinfo']).stdout
    devices={}
    for role in ('source','destination'):
        mount=covering(parse(inventory),'/exports/profile-'+role)
        assert mount['filesystem']=='tmpfs' and mount['point']=='/exports/profile-'+role
        devices[role]=mount['device']
    return dict(container=info['Id'],pid=info['State']['Pid'],started_at=info['State']['StartedAt'],
                mount_namespace=run(['exec',keeper,'readlink','/proc/self/ns/mnt']).stdout.strip(),
                inventory=inventory,devices=devices)


def role_binds(role_volumes,target,readonly=False):
    # The local driver owns the mounts; the live keeper retains their references.
    # Acceptance still proves all three containers see the same two devices.
    result=[]
    for role,name in zip(('source','destination'),role_volumes):
        result+=['--volume',name+':'+target+'/profile-'+role+(':ro' if readonly else '')]
    return result


def verify_binds(run,container,target,devices,readonly=False):
    inventory=run(['exec',container,'cat','/proc/self/mountinfo']).stdout
    for role in ('source','destination'):
        mount=covering(parse(inventory),target+'/profile-'+role)
        assert mount['device']==devices[role] and mount['filesystem']=='tmpfs'
        assert mount['point']==target+'/profile-'+role
        if readonly:assert 'ro' in mount['vfs']
    return inventory


