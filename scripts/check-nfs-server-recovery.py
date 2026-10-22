#!/usr/bin/env python3
"""Prove owned NFSD/container recovery capability; not a NAS/VM reboot test."""
import base64
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import ipaddress
import json
from pathlib import Path
import subprocess
import time
import traceback
import uuid
from nfs_reply_relay import ReplyRelay
from nfs_sync_support import start_trace, finish_trace


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mover',action='store_true',help='Also run four actual source-copy recovery cases after native controls')
    parser.add_argument('--production-gate',type=Path)
    parser.add_argument('--qualification-gate',type=Path)
    parser.add_argument('--distinct-filesystems',action='store_true',help='Retain two bounded filesystems in a separate storage keeper')
    parser.add_argument('--verify-recovery',action='store_true',help='Test destination staging reread across controlled restart')
    parser.add_argument('--publication-recovery',action='store_true',help='Test removal of the staging alias during file publication')
    parser.add_argument('--manifest-recovery',action='store_true',help='Test removal of the staging alias during manifest commitment')
    parser.add_argument('--payload-link-recovery',action='store_true',help='Test initial payload LINK across controlled server restart')
    parser.add_argument('--manifest-link-recovery',action='store_true',help='Test initial manifest LINK across controlled server restart')
    parser.add_argument('--publication-sync-discovery',action='store_true',help='Observe exact publication file fsync with healthy or stopped NFSD')
    parser.add_argument('--payload-link-death-recovery',action='store_true',help='Kill the coordinator during pending payload LINK and recover only after old worker exit')
    parser.add_argument('--manifest-link-death-recovery',action='store_true',help='Kill the coordinator during pending manifest LINK and recover after actual old worker exit')
    parser.add_argument('--claim-link-death-recovery',action='store_true',help='Test source-claim LINK coordinator death before confirmed HTTP 202')
    args=parser.parse_args()
    if args.claim_link_death_recovery and (args.manifest_link_death_recovery or args.payload_link_death_recovery or args.verify_recovery or args.publication_recovery or args.manifest_recovery or args.payload_link_recovery or args.manifest_link_recovery or args.publication_sync_discovery or not (args.mover and args.distinct_filesystems)):parser.error('--claim-link-death-recovery requires --mover --distinct-filesystems and excludes other phases')
    if args.manifest_link_death_recovery:
        if args.payload_link_death_recovery or args.verify_recovery or args.publication_recovery or args.manifest_recovery or args.payload_link_recovery or args.manifest_link_recovery or args.publication_sync_discovery or not (args.mover and args.distinct_filesystems):parser.error('--manifest-link-death-recovery requires --mover --distinct-filesystems and excludes other phases')
        args.manifest_link_recovery=True
    if args.payload_link_death_recovery:
        if args.verify_recovery or args.publication_recovery or args.manifest_recovery or args.payload_link_recovery or args.manifest_link_recovery or args.publication_sync_discovery or not (args.mover and args.distinct_filesystems):parser.error('--payload-link-death-recovery requires --mover --distinct-filesystems and excludes other phases')
        args.payload_link_recovery=True
    if args.publication_sync_discovery and (args.verify_recovery or args.publication_recovery or args.manifest_recovery or args.payload_link_recovery or args.manifest_link_recovery or not (args.mover and args.distinct_filesystems)):parser.error('--publication-sync-discovery requires --mover --distinct-filesystems and excludes other phases')
    if args.manifest_link_recovery and (args.verify_recovery or args.publication_recovery or args.manifest_recovery or args.payload_link_recovery or not (args.mover and args.distinct_filesystems)):parser.error('--manifest-link-recovery requires --mover --distinct-filesystems and excludes other recovery phases')
    if args.payload_link_recovery and (args.verify_recovery or args.publication_recovery or args.manifest_recovery or not (args.mover and args.distinct_filesystems)):parser.error('--payload-link-recovery requires --mover --distinct-filesystems and excludes other recovery phases')
    if args.manifest_recovery and (args.verify_recovery or args.publication_recovery or not (args.mover and args.distinct_filesystems)):parser.error('--manifest-recovery requires --mover --distinct-filesystems and excludes other recovery phases')
    if args.publication_recovery and (args.verify_recovery or not (args.mover and args.distinct_filesystems)):parser.error('--publication-recovery requires --mover --distinct-filesystems and excludes --verify-recovery')
    if args.verify_recovery and not (args.mover and args.distinct_filesystems):parser.error('--verify-recovery requires --mover --distinct-filesystems')
    if args.distinct_filesystems and not args.mover:parser.error('--distinct-filesystems requires --mover for controlled NFSD-quiesced restart')
    if args.mover and not (args.production_gate and args.qualification_gate):parser.error('both SLES gate directories are required')
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root/'scripts/rust-platform.json').read_text(encoding='utf-8'))
    label = ('claim-link-death-recovery-' if args.claim_link_death_recovery else 'manifest-link-death-recovery-' if args.manifest_link_death_recovery else 'payload-link-death-recovery-' if args.payload_link_death_recovery else 'publication-sync-discovery-' if args.publication_sync_discovery else 'manifest-link-server-recovery-' if args.manifest_link_recovery else 'payload-link-server-recovery-' if args.payload_link_recovery else 'manifest-server-recovery-' if args.manifest_recovery else 'publication-server-recovery-' if args.publication_recovery else 'verify-server-recovery-' if args.verify_recovery else 'distinct-server-recovery-' if args.distinct_filesystems else 'server-mover-recovery-' if args.mover else 'server-recovery-')+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    output = root/'rust/validation'/label; output.mkdir()
    print('Server recovery: '+str(output), flush=True)
    engine = ['podman','--connection','podman-machine-default-root']
    network = 'bfm-'+label; volume = network+'-export'
    containers, mounts, tasks = [], [], []
    server = client = reader = relay = None
    keeper=None
    role_volumes=[]
    network_created = volume_created = False
    report = dict(status='FAILED',run_id=label,config=config,rust_executed=False,
                  production_nfs_enabled=False,source_deletion_enabled=False,
                  cases=[],cleanup_errors=[],sources={})
    for name in ('check-nfs-server-recovery.py','nfs_recovery_server.sh','nfs_recovery_probe.c',
                 'nfs_reply_relay.py','nfs_reply_proxy.py','nfs_rpc.py','test_nfs_rpc.py',
                 'nfs_sync_support.py','nfs_syscall_trace.py',
                 *(('nfs_server_mover.py','nfs_runtime.py','nfs_binding.py','nfs_mount_profile.py','check-rust-sles.py') if args.mover else ())):
        data=(root/'scripts'/name).read_bytes()
        report['sources'][name]=dict(sha256=hashlib.sha256(data).hexdigest(),base64=base64.b64encode(data).decode())
    if args.distinct_filesystems:
        for name in ('nfs_distinct_storage.py','nfs_recovery_storage.sh'):
            data=(root/'scripts'/name).read_bytes()
            report['sources'][name]=dict(sha256=hashlib.sha256(data).hexdigest(),base64=base64.b64encode(data).decode())
    report['distinct_filesystems']=args.distinct_filesystems
    report['verification_recovery']=args.verify_recovery
    report['publication_recovery']=args.publication_recovery
    report['manifest_recovery']=args.manifest_recovery
    report['payload_link_recovery']=args.payload_link_recovery
    report['payload_link_death_recovery']=args.payload_link_death_recovery
    report['manifest_link_recovery']=args.manifest_link_recovery
    report['manifest_link_death_recovery']=args.manifest_link_death_recovery
    report['claim_link_death_recovery']=args.claim_link_death_recovery
    if args.claim_link_death_recovery:
        data=(root/'scripts/nfs_claim_death_recovery.py').read_bytes()
        report['sources']['nfs_claim_death_recovery.py']=dict(sha256=hashlib.sha256(data).hexdigest(),base64=base64.b64encode(data).decode())
    report['publication_sync_discovery']=args.publication_sync_discovery
    if args.publication_sync_discovery:
        data=(root/'scripts/nfs_publication_sync_discovery.py').read_bytes()
        report['sources']['nfs_publication_sync_discovery.py']=dict(sha256=hashlib.sha256(data).hexdigest(),base64=base64.b64encode(data).decode())
    if args.verify_recovery or args.publication_recovery or args.manifest_recovery or args.payload_link_recovery or args.manifest_link_recovery or args.publication_sync_discovery or args.claim_link_death_recovery:
        data=(root/'scripts/nfs_io_trace.py').read_bytes()
        report['sources']['nfs_io_trace.py']=dict(sha256=hashlib.sha256(data).hexdigest(),base64=base64.b64encode(data).decode())

    def run(args, check=True):
        value=subprocess.run(engine+args,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=45)
        if check and value.returncode: raise RuntimeError(str(args)+': '+value.stdout+value.stderr)
        return value

    def execute(script, user=None, check=True):
        return run(['exec',*(['--user',user] if user else []),client,'/bin/sh','-eu','-c',script],check)

    def state():
        info=json.loads(run(['inspect',server]).stdout)[0]
        result=dict(container=info['Id'],started_at=info['State']['StartedAt'],pid=info['State']['Pid'],
                    image=info['Image'],mounts=info['Mounts'],
                    address=info['NetworkSettings']['Networks'][network]['IPAddress'],
                    threads=run(['exec',server,'cat','/proc/fs/nfsd/threads']).stdout.strip(),
                    boot_id=run(['exec',server,'cat','/proc/sys/kernel/random/boot_id']).stdout.strip(),
                    netns=run(['exec',server,'readlink','/proc/self/ns/net']).stdout.strip(),
                    exports=run(['exec',server,'exportfs','-v']).stdout)
        if keeper:
            from nfs_distinct_storage import storage_state,verify_binds
            result['storage']=storage_state(run,keeper)
            assert result['storage']==report['storage']['before'],'storage keeper identity or mounts changed'
            result['backing_inventory']=verify_binds(run,server,'/exports',result['storage']['devices'])
        return result

    def snapshot(path):
        text=run(['exec','--user','1000:1000',reader,'/bin/sh','-eu','-c',
                  "stat -c '%d:%i:%h:%s' "+path+'; sha256sum '+path]).stdout.splitlines()
        return dict(identity=text[0],sha256=text[1].split()[0])

    def restore(kind):
        if kind=='nfsd':
            run(['exec',server,'rpc.nfsd','-G','10','-L','10','-V','4','-p','2049','2'])
        else:
            if json.loads(run(['inspect',server]).stdout)[0]['State']['Status']=='stopping':
                run(['wait',server])
            run(['start',server])
            assert json.loads(run(['inspect',server]).stdout)[0]['NetworkSettings']['Networks'][network]['IPAddress']==report['static_server_address']
            for _ in range(45):
                if run(['exec',server,'test','-e','/proc/fs/nfsd/threads'],False).returncode==0:
                    if run(['exec',server,'cat','/proc/fs/nfsd/threads'],False).stdout.strip()=='2':break
                time.sleep(.25)
            else:raise AssertionError('restarted server did not start NFSD')

    try:
        report['baseline_inventory']=dict(containers=run(['ps','-a','--format','{{.ID}}']).stdout.splitlines(),
            volumes=run(['volume','ls','--format','{{.Name}}']).stdout.splitlines(),
            networks=run(['network','ls','--format','{{.Name}}']).stdout.splitlines())
        assert not report['baseline_inventory']['containers'], 'another rootful lab is active'
        report['server_image']=run(['image','inspect','localhost/background-file-mover-e2-nfs','--format','{{.Id}}']).stdout.strip()
        run(['network','create','--internal',network]);network_created=True
        report['network']=json.loads(run(['network','inspect',network]).stdout)[0]
        subnet=ipaddress.ip_network(report['network']['subnets'][0]['subnet'])
        server_address=str(subnet.network_address+2)
        assert server_address!=report['network']['subnets'][0]['gateway']
        report['static_server_address']=server_address
        run(['volume','create',volume]);volume_created=True
        report['volume']=json.loads(run(['volume','inspect',volume]).stdout)[0]
        server_binds=[];reader_binds=[]
        if args.distinct_filesystems:
            from nfs_distinct_storage import create_storage,role_binds
            keeper=create_storage(run,root,volume,'localhost/background-file-mover-e2-nfs',containers,report,role_volumes)
            server_binds=role_binds(role_volumes,'/exports')
            reader_binds=role_binds(role_volumes,'/e',readonly=True)
        report['server_cgroup_setting']='default'
        report['server_termination_profile']='nfsd-quiesce-then-sigkill-wait-start' if args.mover else 'abrupt-sigkill-wait-start'
        server=run(['create',
                    '--privileged','--network',network,'--ip',server_address,'--volume',volume+':/exports',*server_binds,
                    '--entrypoint','/bin/sh','localhost/background-file-mover-e2-nfs','/tmp/nfs_recovery_server.sh']).stdout.strip()
        containers.append(server)
        report['server_host_config']=json.loads(run(['inspect',server]).stdout)[0]['HostConfig']
        run(['cp',str(root/'scripts/nfs_recovery_server.sh'),server+':/tmp/nfs_recovery_server.sh'])
        run(['start',server])
        for _ in range(45):
            if 'NFS_RECOVERY_READY' in run(['logs',server]).stdout:break
            time.sleep(.5)
        else:raise AssertionError('server did not become ready')
        report['initial_server']=state();address=report['initial_server']['address']
        client=run(['create','--network',network,'--cap-drop','all','--cap-add','SYS_ADMIN',
                    '--cap-add','SYS_PTRACE','--cap-add','DAC_READ_SEARCH','--security-opt','no-new-privileges',
                    '--entrypoint','/bin/sh',config['runtime'],'-c','exec sleep infinity']).stdout.strip()
        containers.append(client);run(['start',client])
        report['glibc']=execute('getconf GNU_LIBC_VERSION').stdout.strip();assert report['glibc']=='glibc 2.22'
        report['kernel']=execute('uname -r').stdout.strip()
        report['client_security']=execute('cat /proc/1/status').stdout
        execute('mkdir /tmp/recovery-source /tmp/recovery-destination /tmp/control; chmod 777 /tmp/control')
        reader=run(['create','--network','none','--cap-drop','all','--security-opt','no-new-privileges',
                    '--volume',volume+':/e:ro',*reader_binds,'--entrypoint','/bin/sh',config['builder'],'-c','exec sleep infinity']).stdout.strip()
        containers.append(reader);run(['start',reader]);report['storage_reader']=reader
        if keeper:
            from nfs_distinct_storage import verify_binds
            report['storage']['reader_inventory']=verify_binds(run,reader,'/e',report['storage']['before']['devices'],readonly=True)
        builder=run(['create','--network','none','--cap-drop','all','--entrypoint','/bin/sh',config['builder'],'-c','exec sleep infinity']).stdout.strip()
        containers.append(builder);run(['start',builder])
        run(['cp',str(root/'scripts/nfs_recovery_probe.c'),builder+':/tmp/probe.c'])
        run(['exec','--user','1000:1000','--env','ZIG_GLOBAL_CACHE_DIR=/tmp/zig-global','--env','ZIG_LOCAL_CACHE_DIR=/tmp/zig-local',
             builder,'zig','cc','-target','x86_64-linux-gnu.2.22','-O2','-Wall','-Wextra','-Werror','/tmp/probe.c','-o','/tmp/probe'])
        elf=run(['exec',builder,'readelf','-W','-h','-l','-d','--dyn-syms','/tmp/probe']).stdout
        spec=importlib.util.spec_from_file_location('sles_gate',root/'scripts/check-rust-sles.py')
        gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
        run(['cp',builder+':/tmp/probe',str(output/'probe')]);run(['cp',str(output/'probe'),client+':/tmp/probe']);execute('chmod 555 /tmp/probe')
        report['probe']=dict(sha256=hashlib.sha256((output/'probe').read_bytes()).hexdigest(),elf=gate.audit(elf),elf_text=elf)
        relay=ReplyRelay(run,network,config['builder'],address,containers,output)
        report['relay']=relay.evidence
        for role in ('source','destination'):
            point='/tmp/recovery-'+role
            run(['exec',client,'mount','-i','-t','nfs4','-o',
                 'addr='+relay.address+',vers=4.1,proto=tcp,port=2049,sec=sys,hard,ac,async,timeo=10,retrans=1',
                 relay.address+':/profile-'+role,point]);mounts.append(point)
        report['inventory']=execute('cat /proc/self/mountinfo').stdout
        if keeper:
            from nfs_mount_profile import covering,parse
            observed=[covering(parse(report['inventory']),'/tmp/recovery-'+role) for role in ('source','destination')]
            assert observed[0]['device']!=observed[1]['device'],'NFS mounts coalesced onto one client filesystem'
            report['storage']['client_devices']=[m['device'] for m in observed]
        for kind in ('nfsd','container'):
            for role in ('source','destination'):
                name=kind+'-'+role;path='/tmp/recovery-'+role+'/'+name
                control='/tmp/control/'+name;remote='/e/profile-'+role+'/'+name
                row=dict(kind=kind,role=role,path=path,passed=False);report['cases'].append(row)
                print('Recovery capability '+name,flush=True)
                log=(output/(name+'.log')).open('w',encoding='utf-8')
                process=subprocess.Popen(engine+['exec','--user','1000:1000','--env','LD_BIND_NOW=1',client,
                    '/tmp/probe',path,control+'.opened',control+'.begin',control+'.ready',control+'.go',control+'.done'],stdout=log,stderr=log)
                tasks.append((process,log,control))
                for _ in range(50):
                    ready=execute('cat '+control+'.opened','1000:1000',False)
                    if ready.returncode==0:break
                    assert process.poll() is None;time.sleep(.1)
                else:raise AssertionError('probe did not open')
                pid,fd=map(int,ready.stdout.split());row.update(pid=pid,fd=fd)
                row['probe_security']=execute(f'cat /proc/{pid}/status').stdout
                observer=start_trace(run,client,pid,containers,config)
                row['clock_namespaces']={actor:run(['exec',actor,'readlink','/proc/self/ns/time']).stdout.strip()
                    for actor in (client,observer,relay.container)}
                assert len(set(row['clock_namespaces'].values()))==1
                relay.command('observe');execute('touch '+control+'.begin','1000:1000')
                for _ in range(50):
                    if execute('test -f '+control+'.ready','1000:1000',False).returncode==0:break
                    assert process.poll() is None;time.sleep(.1)
                else:raise AssertionError('initial write did not complete')
                row['before_file']=snapshot(remote);assert row['before_file']['sha256']==hashlib.sha256(b'A'*4096).hexdigest()
                row['before_server']=state();row['before_wire']=relay.command('checkpoint')
                if kind=='nfsd':
                    run(['exec',server,'rpc.nfsd','0'])
                    row['stopped_server']=state();assert row['stopped_server']['threads']=='0'
                else:
                    if args.mover:
                        run(['exec',server,'rpc.nfsd','0'])
                        row['quiesced_server']=state();assert row['quiesced_server']['threads']=='0'
                    run(['kill','--signal','KILL',server])
                    row['stop_exit_code']=int(run(['wait',server]).stdout.strip())
                    row['stopped_container']=json.loads(run(['inspect',server]).stdout)[0]['State']
                    assert row['stop_exit_code']==137 and row['stopped_container']['Status']=='exited' and row['stopped_container']['Pid']==0
                    assert not row['stopped_container']['Running']
                row['file_while_stopped']=snapshot(remote);assert row['file_while_stopped']==row['before_file']
                execute('touch '+control+'.go','1000:1000')
                for _ in range(50):
                    raw=execute(f'cat /proc/{pid}/stat',check=False)
                    if raw.returncode==0 and raw.stdout.rsplit(') ',1)[1].split()[0]=='D':break
                    assert process.poll() is None;time.sleep(.1)
                else:raise AssertionError('no actual blocked native probe')
                row['blocked_stat']=raw.stdout;row['blocked_syscall']=execute(f'cat /proc/{pid}/syscall').stdout.strip()
                fields=row['blocked_syscall'].split();assert fields[0] in ('18','74') and int(fields[1],16)==fd
                row['blocked_fd_path']=execute(f'readlink /proc/{pid}/fd/{fd}').stdout.strip();assert row['blocked_fd_path']==path
                row['blocked_relay']=relay.state();assert process.poll() is None
                row['restore_started_ns']=int(run(['exec',relay.container,'python3','-c','import time; print(time.monotonic_ns())']).stdout)
                restore(kind)
                assert process.wait(timeout=90)==0
                row['trace']=finish_trace(run,observer);row['wire']=relay.command('stop_observe')
                row['after_server']=state();row['after_file']=snapshot(remote)
                row['probe_output']=(output/(name+'.log')).read_text(encoding='utf-8')
                assert row['after_file']['identity']==row['before_file']['identity']
                assert row['after_file']['sha256']==hashlib.sha256(b'B'*4096).hexdigest()
                assert row['before_server']['boot_id']==row['after_server']['boot_id']
                assert row['before_server']['address']==row['after_server']['address']==address
                row['passed']=True;print('Recovery capability '+name+': PASS',flush=True)
        if args.mover:
            from nfs_server_mover import qualify_mover
            qualify_mover(root,args.production_gate,args.qualification_gate,run,execute,client,server,
                          output,containers,config,relay,state,restore,snapshot,report)
        report['status']='PASSED'
    except Exception as error:
        report.update(error=str(error),traceback=traceback.format_exc())
    finally:
        if server and mounts:
            try:
                info=json.loads(run(['inspect',server]).stdout)[0]
                if not info['State']['Running']:restore('container')
                elif run(['exec',server,'cat','/proc/fs/nfsd/threads'],False).stdout.strip()!='2':restore('nfsd')
            except Exception as error:report['cleanup_errors'].append('restore: '+str(error))
        if relay:
            try:relay.release()
            except Exception as error:report['cleanup_errors'].append('relay: '+str(error))
        for process,log,control in tasks:
            try:
                if process.poll() is None:
                    execute('touch '+control+'.begin '+control+'.go','1000:1000')
                    process.wait(timeout=90)
                log.close()
            except Exception as error:report['cleanup_errors'].append('probe: '+str(error))
        for point in reversed(mounts):
            try:run(['exec',client,'umount',point])
            except Exception as error:report['cleanup_errors'].append('unmount: '+str(error))
        if not report['cleanup_errors']:
            if server:run(['exec',server,'rpc.nfsd','0'],False);run(['exec',server,'exportfs','-au'],False)
            for target in reversed(containers):
                if target==keeper:
                    from nfs_distinct_storage import storage_state
                    report['storage']['after']=storage_state(run,keeper)
                    assert report['storage']['after']==report['storage']['before']
                if run(['rm','--force',target],False).returncode:report['cleanup_errors'].append('remove '+target)
            for name in reversed(role_volumes):
                if run(['volume','rm',name],False).returncode:report['cleanup_errors'].append('volume '+name)
            if volume_created and run(['volume','rm',volume],False).returncode:report['cleanup_errors'].append('volume '+volume)
            if network_created and run(['network','rm',network],False).returncode:report['cleanup_errors'].append('network '+network)
        if report['cleanup_errors']:report['status']='FAILED'
        report['resources']=dict(containers=containers,mounts=mounts,volume=volume,role_volumes=role_volumes,network=network)
        (output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
        print(report['status']+': '+str(output),flush=True)
        if report.get('error'):print(report['error'],flush=True)
    return 0 if report['status']=='PASSED' else 1


if __name__=='__main__':raise SystemExit(main())
