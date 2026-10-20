"""Actual manifest RPC discovery and positive withholding controls only."""
import base64
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from nfs_bootstrap_state import receipt_evidence
from nfs_io_analysis import analyze
from nfs_mount_profile import covering, parse
from nfs_reply_relay import ReplyRelay
from nfs_runtime import run_runtime
from nfs_sync_support import start_trace, finish_trace


def sha(data):
    return hashlib.sha256(data).hexdigest()


def manifest_data(obj, submission):
    data=base64.b64decode(obj['base64'],validate=True)
    assert sha(data)==obj['sha256'] and len(data)==int(obj['identity'].split(':')[3])
    value=json.loads(data)
    assert value['version']==1 and value['job_id']=='1' and value['generator_id']=='fixture'
    assert value['submission_id']==submission and value['instance_id']
    assert value['files']==[dict(file_id='0',path='nested/data.bin',size_bytes=2097169,
        algorithm='sha256',sha256=sha(bytes(2097152)+b'0123456789abcdefg'))]
    return data


def discover(trace,wires,target,obj):
    """Require descriptor/fsid/fileid, actual bytes and paired successful RPC."""
    analysis=analyze(trace,wires)
    data=base64.b64decode(obj['base64']);selected=[]
    witnesses={}
    for m in analysis['metadata_matches']:
        witnesses.setdefault(m['mount_id'],set()).add(tuple(m['fsid']))
    assert all(len(v)==1 for v in witnesses.values())
    for request in analysis['rpc_operations']:
        identity=analysis['filehandle_identities'].get(request['filehandle_sha256'])
        if not identity:continue
        overlaps=[]
        for index in request['anchored_descriptor_events']:
            event=trace['events'][index];fd=event.get('descriptor')
            if (fd and fd['path']==target and fd['inode']==identity['identity']['fileid']
                    and witnesses.get(fd['mount_id'])=={tuple(identity['identity']['fsid'])}
                    and event['result']==0 and event['syscall'] in (74,91)):
                overlaps.append(index)
            elif (fd and fd['path']==target and event['syscall'] in (1,18) and event['result']==len(data)
                  and fd['inode']==identity['identity']['fileid']
                  and witnesses.get(fd['mount_id'])=={tuple(identity['identity']['fsid'])}):
                overlaps.append(index)
        if not overlaps:continue
        role=request['relay_role'];wire=wires[role]['trace']
        calls=[r for r in wire if r['direction']=='call' and r['sha256']==request['request_sha256']]
        assert len(calls)==1
        call=calls[0]
        replies=[r for r in wire if r['direction']=='reply' and r['connection']==call['connection']
                 and r['xid']==call['xid'] and r['monotonic_ns']>=call['monotonic_ns'] and r['decoded']]
        assert len(replies)==1 and replies[0]['decoded']['status']==0
        op=request['operation'];result=next(o for o in replies[0]['decoded']['operations'] if o['op']==op['op'])
        assert result['status']==0
        if op['op']==38:
            assert op['offset']==0 and op['count']==len(data)==result['count'] and op['data_sha256']==sha(data)
            assert 0<=op['stable']<=result['committed']<=2
            # Match the exact application buffer too, even if the kernel flushes later.
            assert any(e['syscall'] in (1,18) and (e.get('descriptor') or {}).get('path')==target
                       and e['result']==len(data) and 'payload' in e and e['payload']['sha256']==sha(data)
                       and e['enter_ns']<=call['monotonic_ns'] for e in trace['events'])
        selected.append(dict(**request,descriptor_events=overlaps,reply_sha256=replies[0]['sha256'],result=result))
    writes=[r for r in selected if r['operation']['op']==38]
    assert len(writes)==1,'require one complete, attributed manifest WRITE'
    fh=writes[0]['filehandle_sha256']
    assert all(r['filehandle_sha256']==fh for r in selected)
    return dict(analysis=analysis,manifest_operations=selected,write=writes[0],
                commit_requests=sum(r['operation']['op']==5 and r['filehandle_sha256']==fh for r in analysis['rpc_operations']))


def held_manifest(state,obj):
    assert state['armed'] and state['operation']==38 and len(state['held'])==1
    assert not any(state[k] for k in ('forwarded','released','dropped','errors'))
    item=state['held'][0];ops=item['request']['decoded']['operations']
    assert [o['op'] for o in ops]==[53,22,38]
    op=ops[-1];result=next(o for o in item['reply']['operations'] if o['op']==38)
    assert item['xid']==item['request']['decoded']['xid']==item['reply']['xid']
    assert item['reply']['status']==result['status']==0
    assert op['offset']==0 and op['count']==result['count']==int(obj['identity'].split(':')[3])
    assert op['data_sha256']==obj['sha256'] and 0<=op['stable']<=result['committed']<=2
    return dict(filehandle_sha256=ops[1]['filehandle_sha256'],requested_stable=op['stable'],committed=result['committed'],
                count=op['count'],sha256=op['data_sha256'],verifier_hex=result['verifier_hex'])


def qualify_manifest(run,execute,client,server,output,unmount_all,report,binaries,fixture):
    config,containers=fixture['config'],fixture['containers']
    report.update(matrix='manifest-capability',relays={},discoveries=[],
                  declared_cases='Four healthy manifest traces, then four successful WRITE hold/release controls; no reply drop or coordinator death.')
    tested=subprocess.run([sys.executable,str(Path(__file__).with_name('test_nfs_manifest_capability.py')),'-v'],capture_output=True,text=True,timeout=20)
    report['proof_tests']=dict(passed=tested.returncode==0,output=tested.stdout+tested.stderr)
    assert tested.returncode==0
    execute('umask 077; mkdir /tmp/local','1000:1000')
    artifacts={}
    for profile in ('debug','release'):
        execute('cp '+binaries['qualification',profile]+' /tmp/qualification-'+profile+'; chmod 555 /tmp/qualification-'+profile)
        artifacts['qualification-'+profile]=report['gates']['qualification']['artifacts'][profile]['sha256']
    def adapted(script,user=None,check=True,target=None):
        assert target in (None,client)
        return run(['exec',*(['--user',user] if user else []),client,'/bin/sh','-eu','-c',script],check=check)
    def spawn(script,name,target=None):
        assert target in (None,client)
        with (output/(name+'.log')).open('w',encoding='utf-8') as log:
            return subprocess.Popen(['podman','--connection','podman-machine-default-root','exec','--user','1000:1000',
                '--env','LD_BIND_NOW=1',client,'/bin/sh','-eu','-c',script],stdout=log,stderr=log)
    relays={role:ReplyRelay(run,fixture['network'],config['builder'],fixture['address'],containers,output) for role in ('source','destination')}
    for role,relay in relays.items():
        report['relays'][role]=dict(relay.evidence,security=run(['exec',relay.container,'cat','/proc/1/status']).stdout)
    def windows(action):return {role:relay.command(action,operation=38) for role,relay in active.items()}
    def obj(path):
        point='/tmp/profile-source' if path.startswith('/tmp/profile-source/') else '/tmp/profile-destination'
        remote=path.replace(point,point.replace('/tmp/','/exports/'),1)
        data=run(['exec',server,'cat',remote]).stdout.encode('utf-8')
        return dict(path=remote,base64=base64.b64encode(data).decode(),sha256=sha(data),
            identity=run(['exec',server,'stat','-c','%d:%i:%h:%s',remote]).stdout.strip(),
            nfsd_threads=run(['exec',server,'cat','/proc/fs/nfsd/threads']).stdout.strip())
    def cases(Case):
        discovered={}
        for action in ('discovery','hold-release'):
            for profile in ('debug','release'):
                c=Case(profile,'publish',suffix='-manifest-'+layout+'-'+action,both_nfs=True)
                r=c.result;r.update(layout=layout,action=action,scenario_id='SC-115',config=c.config)
                report['cases'].append(r);report['rust_executed']=True
                print('Manifest '+layout+' '+profile+' '+action,flush=True)
                try:
                    r['inventory']=execute('cat /proc/self/mountinfo')
                    mounts=[covering(parse(r['inventory']),p) for p in (c.source,c.destination)]
                    assert (mounts[0]==mounts[1])==(layout=='same-share')
                    assert all(c.config[k+'_binding']['nfs_mount']['profile']=='NMP-41B' for k in ('source','destination'))
                    r['original_source']=execute(f"stat -c '%d:%i:%s' {c.source}/current/nested/data.bin; sha256sum {c.source}/current/nested/data.bin",'1000:1000').splitlines()
                    c.start(True);r['accepted']=c.request('POST','/api/v2/jobs',c.body)
                    assert r['accepted'][0]==202 and r['accepted'][1]['source_paths_released']
                    c.await_pause();pid=c.worker;r['coordinator_pid']=c.service_pid()
                    r['worker_security']=execute(f'cat /proc/{pid}/status','1000:1000')
                    sec=dict(l.split(':',1) for l in r['worker_security'].splitlines() if ':' in l)
                    assert sec['Uid'].split()==sec['Gid'].split()==['1000']*4 and sec['NoNewPrivs'].strip()=='1'
                    assert all(int(sec[k],16)==0 for k in ('CapInh','CapPrm','CapEff'))
                    r['database_before']=execute(f"stat -c '%d:%i' {c.base}/state/jobs.sqlite",'1000:1000')
                    r['enrollment_before']=receipt_evidence(c,adapted)
                    execute(f"printf 'next recording' >{c.source}/current/nested/data.bin",'1000:1000')
                    target=c.destination+'/1/.staging/COMMITTED.part';r['target']=target
                    if action=='discovery':
                        observer=start_trace(run,client,int(pid),containers,config,expected_exit='supervised-delivery',io=True)
                        r['clock_namespaces']={actor:run(['exec',actor,'readlink','/proc/self/ns/time']).stdout.strip()
                            for actor in (client,observer,*[x.container for x in active.values()])}
                        assert len(set(r['clock_namespaces'].values()))==1
                        windows('observe')
                    else:
                        assert profile in discovered
                        windows('observe');windows('arm')
                    execute('touch '+c.rendezvous+'/go','1000:1000')
                    if action=='hold-release':
                        for _ in range(40):
                            roles=[role for role,relay in active.items() if relay.state()['held']]
                            if roles:break
                            time.sleep(.1)
                        assert len(roles)==1
                        role=roles[0];r['relay_role']=role;r['held']=active[role].await_held()
                        raw=execute(f'cat /proc/{pid}/syscall').strip();args=raw.split()
                        assert int(args[0]) in (1,18,74,91)
                        fd=int(args[1],16)
                        assert execute(f'readlink /proc/{pid}/fd/{fd}').strip()==target and c.state(pid)=='D'
                        if args[0]=='91':assert int(args[2],16)==0o400
                        r['pending']=dict(syscall=raw,fd=fd,path=target,state='D',fdinfo=execute(f'cat /proc/{pid}/fdinfo/{fd}'))
                        r['server_while_withheld']=obj(target);manifest_data(r['server_while_withheld'],c.label)
                        assert r['server_while_withheld']['nfsd_threads']=='2'
                        info=dict(l.split(':',1) for l in r['pending']['fdinfo'].splitlines() if ':' in l)
                        assert int(info['ino'])==int(r['server_while_withheld']['identity'].split(':')[1])
                        r['held_proof']=held_manifest(r['held'],r['server_while_withheld'])
                        observed=discovered[profile]['write']
                        assert r['held_proof']['requested_stable']==observed['operation']['stable']
                        assert r['held_proof']['committed']==observed['result']['committed']
                        assert int(args[0]) in {discovered[profile]['trace_syscalls'][i] for i in observed['descriptor_events']}
                        started=time.monotonic();assert c.request('GET','/healthz')[0]==200
                        r['health_seconds']=time.monotonic()-started;assert r['health_seconds']<5
                        r['during']=c.request('GET','/api/v2/jobs/1')[1]
                        assert r['during']['state']!='Committed' and r['during']['details']['condition']!='ReviewRequired'
                        assert r['during']['details']['files'][0]['transfer_phase']=='Published'
                        assert c.children()==[pid] and c.service.poll() is None and c.service_pid()==r['coordinator_pid']
                        r['held_replay']=c.request('POST','/api/v2/jobs',c.body)
                        assert r['held_replay'][0]==202 and r['held_replay'][1]['job_id']=='1'
                        remote=r['server_while_withheld']['path'].replace('/.staging/COMMITTED.part','/COMMITTED.json')
                        r['final_absent_while_withheld']=run(['exec',server,'test','!','-e',remote]).returncode==0
                        assert r['final_absent_while_withheld']
                        r['before_release']=active[role].await_held();held_manifest(r['before_release'],r['server_while_withheld'])
                        r['settled']=active[role].command('release',operation=38)
                        for other,relay in active.items():
                            if other!=role:relay.release()
                    if action=='discovery':
                        r['worker_exit']=c.await_exit(pid);c.worker=None
                        r['trace']=finish_trace(run,observer)
                    final=c.recover(restart=False);c.verify()
                    r['wires']=windows('stop_observe')
                    r['server_final']=obj(c.destination+'/1/COMMITTED.json')
                    data=manifest_data(r['server_final'],c.label)
                    assert json.loads(data)==r['manifest']
                    if action=='discovery':
                        r['discovery']=discover(r['trace'],r['wires'],target,r['server_final'])
                        discovered[profile]=dict(r['discovery'],trace_syscalls=[e['syscall'] for e in r['trace']['events']])
                        report['discoveries'].append(dict(layout=layout,profile=profile,write=r['discovery']['write'],commit_requests=r['discovery']['commit_requests']))
                    else:
                        before=r['server_while_withheld'];after=r['server_final']
                        assert before['sha256']==after['sha256'] and before['base64']==after['base64']
                        assert before['identity'].split(':')[:2]==after['identity'].split(':')[:2]
                    assert final['state']=='Committed' and final['details']['files'][0]['attempt']==1 and not final['details']['source_cleanup_enabled']
                    r['source_identity_after']=execute(f"stat -c '%d:%i:%s' {c.source}/.file-mover/1-0/data",'1000:1000').strip()
                    assert r['source_identity_after']==r['original_source'][0]
                    r['database_after']=execute(f"stat -c '%d:%i' {c.base}/state/jobs.sqlite",'1000:1000')
                    r['enrollment_after']=receipt_evidence(c,adapted)
                    assert r['database_before']==r['database_after'] and r['enrollment_before']==r['enrollment_after']
                    assert execute(f'cat {c.source}/current/nested/data.bin','1000:1000')=='next recording'
                    r['replay']=c.request('POST','/api/v2/jobs',c.body)
                    assert r['replay'][0]==202 and r['replay'][1]['job_id']=='1' and c.request('GET','/api/v2/jobs/2')[0]==404
                    assert c.service.poll() is None and c.service_pid()==r['coordinator_pid']
                    stopped=adapted(c.binary+' --stop '+c.config_path,'1000:1000')
                    assert json.loads(stopped.stdout)['phase']=='Stopped' and c.service.wait(timeout=30)==0
                    c.worker=None;r.update(committed=final,source_and_state_preserved=True,passed=True,service_reply_loss_tested=False)
                    print('Manifest '+layout+' '+profile+' '+action+': PASS',flush=True)
                finally:
                    for relay in active.values():relay.release()
                    c.cleanup()
    try:
        for layout in ('same-share','separate-shares'):
            active={'source':relays['source']} if layout=='same-share' else relays
            for role,relay in active.items():
                point='/tmp/profile-'+role;ip=relay.address
                run(['exec',client,'mount','-i','-t','nfs4','-o','addr='+ip+',vers=4.1,proto=tcp,port=2049,sec=sys,hard,timeo=10,retrans=1,ac,async',ip+':/profile-'+role,point])
                fixture['mounts'].append(point)
            run_runtime(run,adapted,spawn,lambda:None,server,output,client,artifacts,report,case_runner=cases,
                nfs_root='/tmp/profile-source',destination_nfs_root='/tmp/profile-destination' if layout=='separate-shares' else None)
            unmount_all()
        assert len(report['cases'])==8 and all(c['passed'] for c in report['cases'])
        report.update(passed=True,scope='Four actual manifest discovery traces and four matched-success hold/release controls. No reply drop, coordinator death, NAS/kernel or power durability qualification.')
    finally:
        for role,relay in relays.items():
            relay.release();report['relays'][role]['final_state']=relay.state(strict=False)
