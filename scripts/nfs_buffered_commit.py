"""Finite private COMMIT/UNSTABLE capability and fchmod recovery qualification.

No production enablement, deadline changes or claims of physical durability.
"""
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from nfs_bootstrap_state import receipt_evidence
from nfs_mount_profile import covering, parse
from nfs_reply_relay import ReplyRelay
from nfs_runtime import run_runtime
from nfs_sync_capability import validate_resend, validate_unstable_resend
from nfs_sync_support import build_probe, start_trace, finish_trace
from nfs_io_analysis import analyze
from nfs_sync_capability import validate_unstable_held, payload_resends


def qualify_buffered_commit(run, execute, client, server, output, unmount_all, report, binaries, fixture, unstable=False, live_loss=False):
    config, containers = fixture['config'], fixture['containers']
    operation=38 if unstable else 5
    label='UNSTABLE WRITE' if unstable else 'COMMIT'
    slug='unstable' if unstable else 'commit'
    scenario='SC-114' if live_loss else ('SC-113' if unstable else 'SC-112')
    matrix='buffered-'+slug+('-live-loss' if live_loss else '')
    actions=('live-drop',) if live_loss else ('live-release','death-drop')
    case_count=4 if live_loss else 8
    expected = hashlib.sha256(bytes(2*1048576)+b'0123456789abcdefg').hexdigest()
    report.update(matrix=matrix, capabilities=[], relays={},
                  declared_cases=('Two layouts: native discovery/release/drop first, then debug/release live-drop; four service cases.' if live_loss else 'Two layouts: native discovery/release/drop first, then debug/release live-release and coordinator-death/drop; eight service cases.'))
    if unstable or live_loss:
        tested=subprocess.run([sys.executable,str(Path(__file__).with_name('test_nfs_write_resend.py')),'-v'],
                              capture_output=True,text=True,timeout=20)
        report['write_resend_tests']=dict(passed=tested.returncode==0,output=tested.stdout+tested.stderr)
        assert tested.returncode==0
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
        return {role: relay.command(action,operation=operation) for role,relay in active.items()}

    def arm(active):
        windows(active,'observe')
        windows(active,'arm')

    def held_relay(active):
        for _ in range(40):
            found=[role for role,relay in active.items() if relay.state()['held']]
            if found:
                assert len(found)==1, found
                role=found[0]
                value=active[role].await_held()
                if unstable: validate_unstable_held(value)
                return role, value
            time.sleep(.1)
        raise AssertionError('no successful '+label+' reply withheld on either transport')

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
            target=('/tmp/profile-source' if layout=='same-share' else '/tmp/profile-destination')+'/'+slug+'-'+layout+'-'+action
            row=dict(action=action,target=target,passed=False);result['probes'].append(row)
            process=spawn(f'exec /tmp/nfs-sync-probe chmod {target} {base}.ready {base}.go',slug+'-'+layout+'-'+action)
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
                    if unstable: validate_unstable_held(row['before_release_or_drop'])
                    row['settled']=active[role].command(action,operation=operation)
                    for other,relay in active.items():
                        if other!=role:relay.release()
                assert process.wait(timeout=30)==0
                row['wires']=windows(active,'stop_observe')
                if action=='discovery':
                    row['trace']=finish_trace(run,observer)
                    row['analysis']=analyze(row['trace'],row['wires'])
                    commits=[op for op in row['analysis']['rpc_operations'] if op['operation']['op']==operation]
                    assert commits and all(any(row['trace']['events'][i]['syscall']==91 for i in op['overlapping_events']) for op in commits)
                    assert all(row['trace']['events'][i]['result']==0 for op in commits for i in op['overlapping_events'] if row['trace']['events'][i]['syscall']==91)
                else:
                    row['wire']=dict(forwarded=row['wires'][role]['forwarded'])
                    if action=='drop':row['resend_validation']=validate_unstable_resend(row) if unstable else validate_resend(row,5)
                    row['server_after']=server_object(target)
                    assert row['server_after']==row['server_while_withheld']
                row['output']=(output/(slug+'-'+layout+'-'+action+'.log')).read_text(encoding='utf-8')
                assert 'fchmod returned 0' in row['output'] and 'fsync returned 0' in row['output']
                row['passed']=True
                print('Native payload '+label+' '+layout+' '+action+': PASS',flush=True)
            finally:
                for relay in active.values():relay.release()
                if process.poll() is None:
                    adapted('touch '+base+'.go','1000:1000',False);process.wait(timeout=30)
        result['passed']=True

    def cases(Case):
        for profile in ('debug','release'):
            for action in actions:
                c=Case(profile,'copy_chunk',suffix='-'+slug+'-'+layout+'-'+action,both_nfs=True)
                r=c.result;r.update(layout=layout,action=action,scenario_id=scenario,config=c.config)
                report['cases'].append(r);report['rust_executed']=True
                print('Payload '+label+' '+layout+' '+profile+' '+action,flush=True)
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
                    if unstable: validate_unstable_held(r['before_release_or_drop'])
                    if action=='death-drop':
                        r['coordinator_pid']=c.service_pid()
                        c.signal(r['coordinator_pid'],'KILL');r['coordinator_exit']=c.service.wait(timeout=10)
                        assert r['coordinator_exit']!=0
                        path=c.base+'/state/instance.lock'
                        before=execute(f"stat -c '%d:%i:%s:%u:%a' {path}",'1000:1000')
                        probe=adapted(f'test -f {path}; flock -n -E 73 {path} true','1000:1000',False)
                        assert probe.returncode==73 and c.state(pid)=='D'
                        assert before==execute(f"stat -c '%d:%i:%s:%u:%a' {path}",'1000:1000')
                        r['orphan_guard_probe']=dict(exit_code=probe.returncode,identity=before,worker_state='D')
                        r['worker_fds']=execute(f'ls -l /proc/{pid}/fd')
                        c.signal(pid,'KILL')
                    if live_loss:
                        r['coordinator_pid']=c.service_pid()
                    r['settled']=active[role].command('drop' if action.endswith('drop') else 'release',operation=operation)
                    for other,relay in active.items():
                        if other!=role:relay.release()
                    if action=='death-drop':
                        r['worker_exit']=c.await_exit(pid);c.worker=None
                        r['server_after_exit']=server_object(target)
                        assert r['server_after_exit']==r['server_while_withheld']
                    if live_loss:
                        samples=[];r['live_recovery_samples']=samples
                        began=time.monotonic()
                        for _ in range(180):
                            assert c.service.poll() is None and c.service_pid()==r['coordinator_pid']
                            started=time.monotonic();health=c.request('GET','/healthz')
                            health_seconds=time.monotonic()-started
                            started=time.monotonic();code,status=c.request('GET','/api/v2/jobs/1')
                            status_seconds=time.monotonic()-started
                            replay=c.request('POST','/api/v2/jobs',c.body)
                            sample=dict(elapsed_seconds=time.monotonic()-began,health_code=health[0],health_seconds=health_seconds,
                                        status_seconds=status_seconds,status_code=code,status=status,replay=replay,
                                        coordinator_pid=c.service_pid(),children=c.children(),original_worker_state=c.state(pid))
                            samples.append(sample)
                            assert health[0]==code==200 and health_seconds<5 and status_seconds<5
                            assert sample['coordinator_pid']==r['coordinator_pid'] and c.service.poll() is None
                            assert replay[0]==202 and replay[1]['job_id']=='1' and replay[1]['source_paths_released']
                            assert status['details']['condition']!='ReviewRequired',status
                            # This finite short-loss case must complete on its original assignment.
                            assert status['details']['files'][0]['attempt']==1
                            assert set(sample['children'])<=set([pid])
                            if status['state']=='Committed':
                                final=status;r['recovered_status']=status;break
                            time.sleep(1)
                        else:raise AssertionError('live coordinator did not recover within 180 samples')
                    else:
                        final=c.recover(restart=action=='death-drop')
                    c.verify()
                    r['wires']=windows(active,'stop_observe')
                    if live_loss:
                        r['wire']=dict(forwarded=r['wires'][role]['forwarded'])
                        selected,r['resend_scope']=payload_resends(r,operation)
                        r['resend_validation']=validate_unstable_resend(selected) if unstable else validate_resend(selected,5)
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
                    print('Payload '+label+' '+layout+' '+profile+' '+action+': PASS',flush=True)
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
        assert len(report['cases'])==case_count and all(c['passed'] for c in report['cases'])
        report.update(passed=True,scope='Matched payload fchmod '+label+' success withheld; six native controls and '+str(case_count)+' bounded service '+('live-drop' if live_loss else 'release/death-drop')+' recoveries. No power durability or general NAS/kernel qualification.')
    finally:
        for role,relay in relays.items():
            relay.release();report['relays'][role]['final_state']=relay.state(strict=False)
