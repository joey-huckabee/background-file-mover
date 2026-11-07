"""Actual supervised service checks; called only inside the owned profile lab."""
import base64
from contextlib import contextmanager
import re
import copy
import hashlib
import json
import subprocess
import tarfile
import time
from nfs_binding import binding_for, provision
from nfs_mount_profile import parse, covering



@contextmanager
def control_traversal(execute, target):
    # Root has SYS_ADMIN, not DAC bypass, and the NAS squashes root. Temporarily
    # permit lookup (never listing/writing) through ONLY these empty-lab ancestors.
    # All service requests occur after restoring original private modes.
    assert re.fullmatch(r'/tmp/profile-(source|destination)/(debug|release)-nmp-41[bn]/\1/unexpected',target)
    approved = target.rsplit('/',1)[0]
    parent = approved.rsplit('/',1)[0]
    assert execute('stat -c %a '+parent+' '+approved,'1000:1000').splitlines()==['700','700']
    execute('chmod 701 '+parent+' '+approved,'1000:1000')
    try:
        yield
    finally:
        execute('chmod 700 '+parent+' '+approved,'1000:1000')


def qualify(root, production_gate, qualification_gate, run, execute, client,
            output, mount, unmount_all, mounts, report, same_share=False, buffered_reads=False,
            buffered_publication=False, server=None, buffered_post_unlink=False, buffered_claims=False, buffered_bootstrap=False, buffered_sync=False, fixture=None, buffered_io=False, buffered_commit=False, buffered_unstable=False, live_loss=False, manifest_capability=False, manifest_loss=False, claim_capability=False, claim_loss=False, source_sync=False):
    report['gates'] = {}
    engine = ['podman', '--connection', 'podman-machine-default-root']
    binaries = {}
    for mode, gate in (('production', production_gate), ('qualification', qualification_gate)):
        assert gate.is_dir(), 'gate directory missing'
        deadline = time.monotonic()+180
        while not (gate/'report.json').exists() and time.monotonic() < deadline:
            time.sleep(.5)
        assert (gate/'report.json').exists(), 'gate did not finish within the bounded wait'
        data = json.loads((gate / 'report.json').read_text(encoding='utf-8'))
        assert data['status'] == 'PASSED' and not data.get('cleanup_error')
        assert data['config'] == json.loads((root/'scripts/rust-platform.json').read_text(encoding='utf-8'))
        assert data['build_mode'] == ('production' if mode == 'production' else 'nfs-qualification')
        archive = gate / 'source.tar.gz'
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == data['source_sha256']
        with tarfile.open(archive) as tar:
            files = {m.name: tar.extractfile(m).read() for m in tar if m.isfile()}
        current = {p.relative_to(root/'rust').as_posix(): p.read_bytes()
                   for child in (root/'rust').iterdir() if child.name not in ('validation','target')
                   for p in (child.rglob('*') if child.is_dir() else [child]) if p.is_file()}
        assert files == current, 'stale source gate'
        report['gates'][mode] = dict(run_id=data['run_id'], source_sha256=data['source_sha256'],
                                    rust_input_count=len(files), artifacts={})
        for profile in ('debug','release'):
            artifact = next(a for a in data['profiles'][profile]['artifacts'] if not a['test'])
            binary = gate / artifact['name']
            assert hashlib.sha256(binary.read_bytes()).hexdigest() == artifact['sha256']
            remote = '/tmp/mount-auth-' + mode + '-' + profile
            run(['cp', str(binary), client + ':' + remote])
            execute('chmod 555 ' + remote)
            assert execute('sha256sum ' + remote, '1000:1000').split()[0] == artifact['sha256']
            binaries[(mode,profile)] = remote
            report['gates'][mode]['artifacts'][profile] = artifact
    execute('umask 077; mkdir /tmp/mount-auth', '1000:1000')
    unmount_all()
    if claim_capability or claim_loss:
        from nfs_claim_capability import qualify_claims
        return qualify_claims(run, execute, client, server, output, unmount_all, report, binaries, fixture, loss=claim_loss)
    if manifest_capability or manifest_loss:
        from nfs_manifest_capability import qualify_manifest
        return qualify_manifest(run, execute, client, server, output, unmount_all, report, binaries, fixture, loss=manifest_loss)
    if buffered_commit or buffered_unstable:
        from nfs_buffered_commit import qualify_buffered_commit
        return qualify_buffered_commit(run, execute, client, server, output, unmount_all, report, binaries, fixture, unstable=buffered_unstable, live_loss=live_loss)
    if source_sync or buffered_sync or buffered_io:
        from nfs_buffered_sync import qualify_buffered_sync
        return qualify_buffered_sync(run, execute, client, server, output, unmount_all, report, binaries, fixture, io_trace=buffered_io, source_sync=source_sync)
    if buffered_bootstrap:
        from nfs_buffered_bootstrap import qualify_buffered_bootstrap
        return qualify_buffered_bootstrap(run, execute, client, server, output, mount, unmount_all, report, binaries)
    if buffered_claims:
        from nfs_buffered_claims import qualify_buffered_claims
        return qualify_buffered_claims(run, execute, client, server, output, mount, unmount_all, report, binaries)
    if buffered_publication or buffered_post_unlink:
        from nfs_buffered_publication import qualify_buffered_publication
        return qualify_buffered_publication(run, execute, client, server, output, mount, unmount_all, report, binaries,
                                           post_unlink=buffered_post_unlink)
    if buffered_reads:
        from nfs_buffered_reads import qualify_buffered_reads
        return qualify_buffered_reads(run, execute, client, server, output, mount, unmount_all, report, binaries)
    if same_share:
        from nfs_same_share import qualify_same_share
        return qualify_same_share(run, execute, client, output, mount, unmount_all, report, binaries)
    counter = 0

    def config_file(config, name):
        local = output / (name + '.json')
        local.write_text(json.dumps(config), encoding='utf-8')
        remote = '/tmp/mount-auth/' + name + '.json'
        staging = '/tmp/mount-auth-config-staging'
        run(['cp', str(local), client + ':' + staging])
        execute('chmod 644 ' + staging)
        execute('umask 077; cat '+staging+' >'+remote, '1000:1000')
        return remote

    def request(method, path, body=None):
        nonlocal counter
        counter += 1
        payload = b'' if body is None else json.dumps(body).encode()
        wire = (f'{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\n\r\n').encode()+payload
        local = output / ('auth-request-'+str(counter))
        local.write_bytes(wire)
        remote = '/tmp/mount-auth/request'
        run(['cp', str(local), client+':'+remote])
        text = execute("/bin/bash -c 'exec 3<>/dev/tcp/127.0.0.1/19879; cat /tmp/mount-auth/request >&3; cat <&3'", '1000:1000')
        head, payload = text.replace('\r\n','\n').split('\n\n',1)
        return int(head.split()[1]), json.loads(payload)

    def await_state(predicate, process):
        deadline = time.monotonic()+30
        last = None
        while time.monotonic() < deadline:
            assert process.poll() is None, 'service exited'
            last = request('GET','/api/v2/jobs/1')
            if last[0] == 200 and predicate(last[1]):
                return last[1]
            time.sleep(.2)
        raise AssertionError('job state timeout: '+str(last))

    for profile in ('debug','release'):
        for cache in ('NMP-41B','NMP-41N'):
            for role in ('source','destination'):
                mount(role, 'hard,ac,async' if cache == 'NMP-41B' else 'hard,noac')
            label = profile+'-'+cache.lower()
            source = '/tmp/profile-source/'+label+'/source'
            destination = '/tmp/profile-destination/'+label+'/destination'
            state = '/tmp/mount-auth/'+label+'/state'
            config = dict(bind='127.0.0.1:19879', generator_id='fixture', source_root=source,
                          destination_root=destination, state_database=state+'/jobs.sqlite')
            execute(f'umask 077; mkdir -p {source}/.file-mover {source}/current/nested {destination}/.file-mover {state}; '
                    f"printf 'original profile payload' >{source}/current/nested/data", '1000:1000')
            def provision_execute(script, user=None, target=None):
                # nfs_binding expects the standard boundary fixture result shape.
                class Response:
                    stdout = execute(script,user)
                return Response()
            for role,path in (('source',source),('destination',destination)):
                binding = binding_for(label+'-'+role,True,role)
                provision(run, provision_execute, output, client, path, binding)
                assert binding['nfs_mount']['profile'] == cache
                config[role+'_binding'] = binding
            config_path = config_file(config,label)
            case = dict(profile=profile, cache_profile=cache, passed=False, source=source,
                        destination=destination, config=config, negative_startups=[])
            report['cases'].append(case)
            case['inventory'] = execute('cat /proc/self/mountinfo')
            # Reject before SQLite/source enrollment. Start with actual declarations
            # from newly provisioned owned fixtures, never migrate an old source.
            for kind in ('wrong-address','missing-declaration','wrong-cache','missing-mountpoint','production-disabled'):
                bad = copy.deepcopy(config)
                bad_state = '/tmp/mount-auth/'+label+'/'+kind
                execute('umask 077; mkdir '+bad_state, '1000:1000')
                bad['state_database'] = bad_state+'/jobs.sqlite'
                if kind == 'wrong-address': bad['source_binding']['nfs_mount']['addr'] = '192.0.2.99'
                if kind == 'missing-declaration': del bad['source_binding']['nfs_mount']
                if kind == 'wrong-cache': bad['source_binding']['nfs_mount']['profile'] = 'NMP-41N' if cache == 'NMP-41B' else 'NMP-41B'
                if kind == 'missing-mountpoint': bad['source_binding']['nfs_mount']['mountpoint'] = '/tmp/absent-mount'
                remote = config_file(bad,label+'-'+kind)
                mode = 'production' if kind == 'production-disabled' else 'qualification'
                report['rust_executed'] = True
                value = run(['exec','--user','1000:1000',client,binaries[(mode,profile)],'--initialize-source',remote],check=False)
                assert value.returncode != 0, kind
                execute('test ! -e '+bad['state_database'], '1000:1000')
                case['negative_startups'].append(dict(kind=kind,exit_code=value.returncode,stderr=value.stderr,database_absent=True))
            binary = binaries[('qualification',profile)]
            case['initialize'] = execute(binary+' --initialize-source '+config_path, '1000:1000')
            case['source_enrollment'] = json.loads(execute('cat '+source+'/.file-mover/source-enrollment.json','1000:1000'))
            assert case['source_enrollment']['binding'] == config['source_binding']
            assert len(case['source_enrollment']['observation'].split(':nmp:')[-1]) == 64
            assert ':nmp:' in case['source_enrollment']['observation']
            case['original_source'] = execute(f"stat -c '%d:%i:%s' {source}/current/nested/data; sha256sum {source}/current/nested/data", '1000:1000').splitlines()
            expected_hash = hashlib.sha256(b'original profile payload').hexdigest()
            processes = []
            def start(suffix):
                log = (output/(label+'-'+suffix+'.log')).open('w',encoding='utf-8')
                process = subprocess.Popen(engine+['exec','--user','1000:1000',client,binary,config_path],stdout=log,stderr=log)
                processes.append((process,log))
                deadline = time.monotonic()+20
                while time.monotonic() < deadline:
                    assert process.poll() is None, 'startup failed; inspect '+log.name
                    try:
                        code, body = request('GET','/healthz')
                        if code == 200 and body.get('status') == 'ok': return process
                        if code == 200: return process
                    except (RuntimeError,ValueError): pass
                    time.sleep(.2)
                raise AssertionError('service not ready')
            def stop(process):
                case.setdefault('stops',[]).append(execute(binary+' --stop '+config_path,'1000:1000'))
                assert process.wait(timeout=30)==0
            try:
                service = start('service')
                body = dict(generator_id='fixture',submission_id=label,source_path=source+'/current',files=[dict(name='nested/data')])
                for root_path in (source,destination):
                    point = root_path+'/unexpected'
                    execute('mkdir -m 755 '+point,'1000:1000')
                    with control_traversal(execute,point):
                        run(['exec',client,'mount','-t','tmpfs','tmpfs',point])
                        mounts.append(point)
                code, pending = request('POST','/api/v2/jobs',body)
                case['source_mount_refusal'] = dict(code=code,body=pending)
                assert code==409 and not pending['source_paths_released']
                assert execute(f"stat -c '%d:%i:%s' {source}/current/nested/data; sha256sum {source}/current/nested/data",'1000:1000').splitlines()==case['original_source']
                with control_traversal(execute,source+'/unexpected'):
                    run(['exec',client,'umount',source+'/unexpected'])
                    mounts.remove(source+'/unexpected')
                code, claimed = request('POST','/api/v2/jobs',body)
                assert code==202 and claimed['job_id']=='1' and claimed['source_paths_released']
                case['claimed'] = claimed
                execute(f"printf 'new recording' >{source}/current/nested/data",'1000:1000')
                refused = await_state(lambda s:(s.get('details',{}).get('delivery_retry') or {}).get('code')=='destination_binding_requires_review',service)
                case['destination_mount_refusal'] = refused
                assert refused['state']=='Claimed' and not refused['details']['source_cleanup_enabled']
                execute(f'test ! -e {destination}/1/COMMITTED.json','1000:1000')
                with control_traversal(execute,destination+'/unexpected'):
                    run(['exec',client,'umount',destination+'/unexpected'])
                    mounts.remove(destination+'/unexpected')
                resume = dict(command_id=label+'-resume',expected_review_epoch=refused['details']['review_epoch'],reason='Restore original fixture mount scope')
                code, resumed = request('POST','/api/v2/jobs/1/resume',resume)
                assert code==200,(code,resumed)
                case['resume'] = resumed
                committed = await_state(lambda s:s['state']=='Committed',service)
                case['committed'] = committed
                case['private_source'] = execute(f"stat -c '%d:%i:%s' {source}/.file-mover/1-0/data; sha256sum {source}/.file-mover/1-0/data",'1000:1000').splitlines()
                assert case['private_source'][0]==case['original_source'][0]
                assert case['private_source'][1].split()[0]==expected_hash
                case['manifest'] = json.loads(execute('cat '+destination+'/1/COMMITTED.json','1000:1000'))
                assert execute('sha256sum '+destination+'/1/nested/data','1000:1000').split()[0]==expected_hash
                assert case['manifest']['files'][0]['sha256']==expected_hash
                assert committed['details']['files'][0]['attempt']==1
                stop(service)
                case['state_before_restart'] = execute(f"stat -c '%d:%i' {state}/jobs.sqlite; sha256sum {source}/.file-mover/source-enrollment.json",'1000:1000')
                service = start('restart')
                code,replay = request('POST','/api/v2/jobs',body)
                assert code==202 and replay['job_id']=='1'
                assert request('GET','/api/v2/jobs/1')[1]['state']=='Committed'
                assert execute('cat '+source+'/current/nested/data','1000:1000')=='new recording'
                case['replay'] = replay
                case['state_after_restart'] = execute(f"stat -c '%d:%i' {state}/jobs.sqlite; sha256sum {source}/.file-mover/source-enrollment.json",'1000:1000')
                assert case['state_before_restart']==case['state_after_restart']
                stop(service)
                # A per-mount VFS flag change keeps the NFS superblock/root
                # identities, isolating the newly persisted mount fingerprint.
                old_custody = execute(f"stat -c '%d:%i:%u:%a' {source} {source}/.file-mover {source}/.file-mover/source-enrollment.json",'1000:1000')
                run(['exec',client,'mount','-i','-o','remount,bind,nosuid','/tmp/profile-source','/tmp/profile-source'])
                case['changed_mount_inventory'] = execute('cat /proc/self/mountinfo')
                assert old_custody == execute(f"stat -c '%d:%i:%u:%a' {source} {source}/.file-mover {source}/.file-mover/source-enrollment.json",'1000:1000')
                changed_start = run(['exec','--user','1000:1000',client,binary,config_path],check=False)
                assert changed_start.returncode != 0 and 'SourceRootChanged' in changed_start.stderr, changed_start.stderr
                case['changed_pin_restart'] = dict(exit_code=changed_start.returncode,stderr=changed_start.stderr,root_custody_unchanged=True)
                assert case['state_after_restart'] == execute(f"stat -c '%d:%i' {state}/jobs.sqlite; sha256sum {source}/.file-mover/source-enrollment.json",'1000:1000')
                assert execute('cat '+source+'/current/nested/data','1000:1000')=='new recording'
                original_mount = covering(parse(case['inventory']),source)
                restore_flags = ','.join(['remount','bind',*original_mount['vfs']])
                run(['exec',client,'mount','-i','-o',restore_flags,'/tmp/profile-source','/tmp/profile-source'])
                assert covering(parse(execute('cat /proc/self/mountinfo')),source)==original_mount
                service = start('restored-pin')
                code, final_replay = request('POST','/api/v2/jobs',body)
                assert code==202 and final_replay['job_id']=='1'
                assert request('GET','/api/v2/jobs/1')[1]['state']=='Committed'
                assert execute('cat '+source+'/current/nested/data','1000:1000')=='new recording'
                case['restored_pin_replay']=final_replay
                stop(service)
                case['passed']=True
            finally:
                for process,log in processes:
                    if process.poll() is None:
                        # Supported bounded controller, never process-name killing.
                        run(['exec','--user','1000:1000',client,binary,'--stop',config_path],check=False)
                        try: process.wait(timeout=30)
                        except subprocess.TimeoutExpired: raise RuntimeError('service survived cleanup; preserve fixture')
                    log.close()
            unmount_all()
    report['passed']=True
