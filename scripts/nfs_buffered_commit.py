"""Finite private COMMIT capability and payload-fchmod recovery qualification.

No production enablement, deadline changes or claims of physical durability.
"""
import hashlib
import json
import subprocess
import time
from nfs_bootstrap_state import receipt_evidence
from nfs_mount_profile import covering, parse
from nfs_reply_relay import ReplyRelay
from nfs_runtime import run_runtime
from nfs_sync_capability import validate_resend
from nfs_sync_support import build_probe, start_trace, finish_trace
from nfs_io_analysis import analyze


def qualify_buffered_commit(run, execute, client, server, output, unmount_all, report, binaries, fixture):
    config, containers = fixture['config'], fixture['containers']
    expected = hashlib.sha256(bytes(2*1048576)+b'0123456789abcdefg').hexdigest()
    report.update(matrix='buffered-commit', capabilities=[], relays={},
                  declared_cases='Two layouts: native discovery/release/drop first, then debug/release live-release and coordinator-death/drop; eight service cases.')
    engine = ['podman', '--connection', 'podman-machine-default-root']
    execute('umask 077; mkdir /tmp/local /tmp/sync-probes', '1000:1000')
    artifacts = {}
    for profile in ('debug', 'release'):
        execute('cp '+binaries[('qualification',profile)]+' /tmp/qualification-'+profile+'; chmod 555 /tmp/qualification-'+profile)
        artifacts['qualification-'+profile] = report['gates']['qualification']['artifacts'][profile]['sha256']

    def adapted(script, user=None, check=True, target=None):
        assert target in (None, client)
        return run(['exec', *(['--user',user] if user else []), client, '/bin/sh','-eu','-c',script],check=check)

    def spawn(script, name, target=None):
        assert target in (None, client)
        with (output/(name+'.log')).open('w',encoding='utf-8') as log:
            return subprocess.Popen(engine+['exec','--user','1000:1000','--env','LD_BIND_NOW=1',client,
                                             '/bin/sh','-eu','-c',script],stdout=log,stderr=log)

    relays = {role: ReplyRelay(run,fixture['network'],config['builder'],fixture['address'],containers,output)
              for role in ('source','destination')}
    for role, relay in relays.items():
        report['relays'][role] = dict(relay.evidence,security=run(['exec',relay.container,'cat','/proc/1/status']).stdout)
    report['probe'] = build_probe(run,output,client,containers,config)

    def windows(active,action):
        return {role: relay.command(action,operation=5) for role,relay in active.items()}

    def arm(active):
        windows(active,'observe')
        windows(active,'arm')

    def held_relay(active):
        for _ in range(40):
            found=[role for role,relay in active.items() if relay.state()['held']]
            if found:
                assert len(found)==1, found
                role=found[0]
                return role, active[role].await_held()
            time.sleep(.1)
        raise AssertionError('no successful COMMIT reply withheld on either transport')

    def pending(pid,target):
        raw=execute(f'cat /proc/{pid}/syscall').strip()
        assert raw.split()[0]=='91', raw
        fd=int(raw.split()[1],16)
        assert int(raw.split()[2],16)==0o400, raw
        path=execute(f'readlink /proc/{pid}/fd/{fd}').strip()
        assert path==target, (path,target)
        state=execute(f'cat /proc/{pid}/stat').rsplit(') ',1)[1].split()[0]
        assert state=='D',state
        return dict(syscall=raw,fd=fd,path=path,state=state,
                    fdinfo=execute(f'cat /proc/{pid}/fdinfo/{fd}'))

    def server_object(target):
        point='/tmp/profile-source' if target.startswith('/tmp/profile-source/') else '/tmp/profile-destination'
        remote=target.replace(point,point.replace('/tmp/','/exports/'),1)
        result=dict(path=remote,identity=run(['exec',server,'stat','-c','%d:%i:%h:%s',remote]).stdout.strip(),
                    sha256=run(['exec',server,'sha256sum',remote]).stdout.split()[0],
                    nfsd_threads=run(['exec',server,'cat','/proc/fs/nfsd/threads']).stdout.strip())
        assert result['sha256']==expected and result['identity'].split(':')[3]==str(2*1048576+17)
        assert result['nfsd_threads']=='2'
        return result

    def capability(layout, active):
        result=dict(layout=layout,probes=[],passed=False)
        report['capabilities'].append(result)
        for action in ('discovery','release','drop'):
            base='/tmp/sync-probes/'+layout+'-'+action
            target=('/tmp/profile-source' if layout=='same-share' else '/tmp/profile-destination')+'/commit-'+layout+'-'+action
            row=dict(action=action,target=target,passed=False);result['probes'].append(row)
            process=spawn(f'exec /tmp/nfs-sync-probe chmod {target} {base}.ready {base}.go','commit-'+layout+'-'+action)
            try:
                for _ in range(30):
                    ready=adapted('cat '+base+'.ready','1000:1000',False)
                    if ready.returncode==0:break
                    assert process.poll() is None;time.sleep(.1)
                else:raise AssertionError('native chmod probe not ready')
                pid,fd=map(int,ready.stdout.split());row.update(pid=pid,fd=fd)
                if action=='discovery':
                    observer=start_trace(run,client,pid,containers,config,io=True)
                    actors=[client,observer,*[v.container for v in active.values()]]
                    row['clock_namespaces']={actor:run(['exec',actor,'readlink','/proc/self/ns/time']).stdout.strip() for actor in actors}
                    assert len(set(row['clock_namespaces'].values()))==1
                    windows(active,'observe')
                else:arm(active)
                execute('touch '+base+'.go','1000:1000')
                if action!='discovery':
                    role,row['held']=held_relay(active);row['relay_role']=role
                    row['pending']=pending(pid,target);assert row['pending']['fd']==fd
                    row['server_while_withheld']=server_object(target)
                    row['before_release_or_drop']=active[role].await_held()
                    row['settled']=active[role].command(action,operation=5)
                    for other,relay in active.items():
                        if other!=role:relay.release()
                assert process.wait(timeout=30)==0
                row['wires']=windows(active,'stop_observe')
                if action=='discovery':
                    row['trace']=finish_trace(run,observer)
                    row['analysis']=analyze(row['trace'],row['wires'])
                    commits=[op for op in row['analysis']['rpc_operations'] if op['operation']['op']==5]
                    assert commits and all(any(row['trace']['events'][i]['syscall']==91 for i in op['overlapping_events']) for op in commits)
                    assert all(row['trace']['events'][i]['result']==0 for op in commits for i in op['overlapping_events'] if row['trace']['events'][i]['syscall']==91)
                else:
                    row['wire']=dict(forwarded=row['wires'][role]['forwarded'])
                    if action=='drop':row['resend_validation']=validate_resend(row,5)
                    row['server_after']=server_object(target)
                    assert row['server_after']==row['server_while_withheld']
                row['output']=(output/('commit-'+layout+'-'+action+'.log')).read_text(encoding='utf-8')
                assert 'fchmod returned 0' in row['output'] and 'fsync returned 0' in row['output']
                row['passed']=True
                print('Native payload COMMIT '+layout+' '+action+': PASS',flush=True)
            finally:
                for relay in active.values():relay.release()
                if process.poll() is None:
                    adapted('touch '+base+'.go','1000:1000',False);process.wait(timeout=30)
        result['passed']=True

    def cases(Case):
        for profile in ('debug','release'):
            for action in ('live-release','death-drop'):
                c=Case(profile,'copy_chunk',suffix='-commit-'+layout+'-'+action,both_nfs=True)
                r=c.result;r.update(layout=layout,action=action,scenario_id='SC-112',config=c.config)
                report['cases'].append(r);report['rust_executed']=True
                print('Payload COMMIT '+layout+' '+profile+' '+action,flush=True)
                try:
                    r['inventory']=execute('cat /proc/self/mountinfo')
                    mounts=[covering(parse(r['inventory']),p) for p in (c.source,c.destination)]
                    assert (mounts[0]==mounts[1])==(layout=='same-share')
                    assert all(c.config[k+'_binding']['nfs_mount']['profile']=='NMP-41B' for k in ('source','destination'))
                    r['original_source']=execute(f"stat -c '%d:%i:%s' {c.source}/current/nested/data.bin; sha256sum {c.source}/current/nested/data.bin",'1000:1000').splitlines()
                    c.start(True)
                    r['accepted']=c.request('POST','/api/v2/jobs',c.body)
                    assert r['accepted'][0]==202 and r['accepted'][1]['source_paths_released']
                    c.await_pause();pid=c.worker
                    r['worker_security']=execute(f'cat /proc/{pid}/status','1000:1000')
                    sec=dict(line.split(':',1) for line in r['worker_security'].splitlines() if ':' in line)
                    assert sec['Uid'].split()==sec['Gid'].split()==['1000']*4
                    assert sec['NoNewPrivs'].strip()=='1' and all(int(sec[k],16)==0 for k in ('CapInh','CapPrm','CapEff'))
                    r['database_before']=execute(f"stat -c '%d:%i' {c.base}/state/jobs.sqlite",'1000:1000')
                    r['enrollment_before']=receipt_evidence(c,adapted)
                    execute(f"printf 'next recording' >{c.source}/current/nested/data.bin",'1000:1000')
                    r['before']=c.request('GET','/api/v2/jobs/1')[1]
                    assert r['before']['details']['files'][0]['transfer_phase']=='Intent'
                    arm(active);execute('touch '+c.rendezvous+'/go','1000:1000')
                    role,r['held']=held_relay(active);r['relay_role']=role
                    target=c.destination+'/1/.staging/1.part'
                    r['pending']=pending(pid,target)
                    r['server_while_withheld']=server_object(target)
                    started=time.monotonic();assert c.request('GET','/healthz')[0]==200
                    r['health_seconds']=time.monotonic()-started;assert r['health_seconds']<5
                    r['during']=c.request('GET','/api/v2/jobs/1')[1]
                    assert r['during']['details']['files']==r['before']['details']['files'] and c.children()==[pid]
                    assert c.request('POST','/api/v2/jobs',c.body)[0]==202
                    r['before_release_or_drop']=active[role].await_held()
                    if action=='death-drop':
                        c.signal(c.service_pid(),'KILL');assert c.service.wait(timeout=10)!=0
                        path=c.base+'/state/instance.lock'
                        before=execute(f"stat -c '%d:%i:%s:%u:%a' {path}",'1000:1000')
                        probe=adapted(f'test -f {path}; flock -n -E 73 {path} true','1000:1000',False)
                        assert probe.returncode==73 and c.state(pid)=='D'
                        assert before==execute(f"stat -c '%d:%i:%s:%u:%a' {path}",'1000:1000')
                        r['orphan_guard_probe']=dict(exit_code=probe.returncode,identity=before,worker_state='D')
                        r['worker_fds']=execute(f'ls -l /proc/{pid}/fd')
                        c.signal(pid,'KILL')
                    r['settled']=active[role].command('drop' if action=='death-drop' else 'release',operation=5)
                    for other,relay in active.items():
                        if other!=role:relay.release()
                    if action=='death-drop':
                        r['worker_exit']=c.await_exit(pid);c.worker=None
                        r['server_after_exit']=server_object(target)
                        assert r['server_after_exit']==r['server_while_withheld']
                    final=c.recover(restart=action=='death-drop');c.verify()
                    r['wires']=windows(active,'stop_observe')
                    attempt=2 if action=='death-drop' else 1
                    assert final['details']['files'][0]['attempt']==attempt and not final['details']['source_cleanup_enabled']
                    if action=='death-drop':
                        r['preserved_partial']=server_object(target)
                        assert r['preserved_partial']==r['server_while_withheld']
                    r['source_identity_after']=execute(f"stat -c '%d:%i:%s' {c.source}/.file-mover/1-0/data",'1000:1000').strip()
                    assert r['source_identity_after']==r['original_source'][0]
                    r['database_after']=execute(f"stat -c '%d:%i' {c.base}/state/jobs.sqlite",'1000:1000')
                    r['enrollment_after']=receipt_evidence(c,adapted)
                    assert r['database_after']==r['database_before'] and r['enrollment_after']==r['enrollment_before']
                    assert execute(f'cat {c.source}/current/nested/data.bin','1000:1000')=='next recording'
                    r['replay']=c.request('POST','/api/v2/jobs',c.body)
                    assert r['replay'][0]==202 and r['replay'][1]['job_id']=='1'
                    assert c.request('GET','/api/v2/jobs/2')[0]==404
                    r.update(committed=final,source_and_state_preserved=True)
                    stopped=adapted(c.binary+' --stop '+c.config_path,'1000:1000')
                    assert json.loads(stopped.stdout)['phase']=='Stopped' and c.service.wait(timeout=30)==0
                    c.worker=None;r['passed']=True
                    print('Payload COMMIT '+layout+' '+profile+' '+action+': PASS',flush=True)
                finally:
                    for relay in active.values():relay.release()
                    c.cleanup()

    try:
        for layout in ('same-share','separate-shares'):
            active={'source':relays['source']} if layout=='same-share' else relays
            for role in active:
                point='/tmp/profile-'+role;ip=relays[role].address
                run(['exec',client,'mount','-i','-t','nfs4','-o',
                     'addr='+ip+',vers=4.1,proto=tcp,port=2049,sec=sys,hard,timeo=10,retrans=1,ac,async',ip+':/profile-'+role,point])
                fixture['mounts'].append(point)
            capability(layout,active)
            run_runtime(run,adapted,spawn,lambda:None,server,output,client,artifacts,report,
                        case_runner=cases,nfs_root='/tmp/profile-source',
                        destination_nfs_root='/tmp/profile-destination' if layout=='separate-shares' else None)
            unmount_all()
        assert len(report['cases'])==8 and all(c['passed'] for c in report['cases'])
        report.update(passed=True,scope='Matched payload fchmod COMMIT success withheld; six native controls and eight bounded service release/death-drop recoveries. No power durability or general NAS/kernel qualification.')
    finally:
        for role,relay in relays.items():
            relay.release();report['relays'][role]['final_state']=relay.state(strict=False)
