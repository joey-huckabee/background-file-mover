"""Fixture-only immutable SQLite intent and FILE_SYNC recovery evidence."""
from contextlib import closing
import base64
import json
from pathlib import Path
import sqlite3
import tempfile
from nfs_manifest_capability import sha


def read_intent(files):
    """Read retained copies only; never attach a live mover database."""
    with tempfile.TemporaryDirectory(prefix='mover-manifest-intent-') as temporary:
        folder=Path(temporary)
        for name,item in files.items():
            assert name in ('jobs.sqlite','jobs.sqlite-wal')
            data=base64.b64decode(item['base64'],validate=True)
            assert sha(data)==item['sha256'] and len(data)==item['size']
            (folder/name).write_bytes(data)
        assert 'jobs.sqlite' in files
        with closing(sqlite3.connect((folder/'jobs.sqlite').as_uri()+'?mode=ro',uri=True)) as db:
            db.execute('PRAGMA query_only=ON')
            assert db.execute('PRAGMA quick_check').fetchall()==[('ok',)]
            rows=db.execute('SELECT job_id,bytes,sha256,phase,object_identity FROM manifests ORDER BY job_id').fetchall()
            assert len(rows)==1 and rows[0][0]==1
            job,body,digest,phase,identity=rows[0]
            assert sha(body.encode('utf-8'))==digest
            instance=db.execute("SELECT value FROM metadata WHERE key='instance_id'").fetchone()
            assert instance and json.loads(body)['instance_id']==instance[0]
            result=dict(job_id=job,bytes_base64=base64.b64encode(body.encode('utf-8')).decode(),
                        sha256=digest,phase=phase,object_identity=identity,instance_id=instance[0])
        # SQLite may construct a disposable SHM index, but must not change the retained DB/WAL.
        for name,item in files.items():assert sha((folder/name).read_bytes())==item['sha256']
        return result


def snapshot_intent(run,client,base,output,label):
    """Caller must first prove all coordinator/SQLite writer threads exited."""
    files={}
    for name in ('jobs.sqlite','jobs.sqlite-wal'):
        remote=base+'/state/'+name
        present=run(['exec',client,'test','-f',remote],check=False).returncode==0
        if not present:
            assert name.endswith('-wal');continue
        before=run(['exec',client,'sha256sum',remote]).stdout.split()[0]
        path=output/(label+'-'+name)
        run(['cp',client+':'+remote,str(path)])
        data=path.read_bytes()
        after=run(['exec',client,'sha256sum',remote]).stdout.split()[0]
        assert before==after==sha(data)
        files[name]=dict(sha256=before,size=len(data),base64=base64.b64encode(data).decode())
    return dict(files=files,intent=read_intent(files),scope='Copies acquired only after coordinator exit; query_only read of disposable host copies.')


def validate_intent(snapshot,obj,phase):
    intent=read_intent(snapshot['files']);assert intent==snapshot['intent']
    assert intent['phase']==phase and intent['sha256']==obj['sha256'] and intent['bytes_base64']==obj['base64']
    parts=intent['object_identity'].split(':')
    assert len(parts)==8 and parts[0]=='1' and int(parts[2])==int(obj['identity'].split(':')[1])
    assert parts[3]=='1000'
    if phase==4:assert int(parts[4])==int(obj['identity'].split(':')[3])
    return intent


def validate_manifest_resend(row,restarted=False):
    def shape(item):return [v['op'] for v in item['request']['decoded']['operations']]
    def manifest_range(item):
        ops=item['request']['decoded']['operations']
        allowed=([53,22,38],[53,22,38,9]) if restarted else ([53,22,38],)
        assert shape(item) in allowed,'unqualified manifest compound shape'
        op=ops[2]
        return (ops[1]['filehandle_sha256'],op['offset'],op['count'],op['data_sha256'])
    assert len(row['settled']['dropped'])==1
    assert shape(row['settled']['dropped'][0])==[53,22,38]
    original_handle=manifest_range(row['settled']['dropped'][0])[0]
    forwarded=[];other=[]
    for item in row['wire']['forwarded']:
        (forwarded if manifest_range(item)[0]==original_handle else other).append(item)
    assert forwarded
    scope=dict(filehandle_sha256=original_handle,selected_receive_ids=[v['receive_id'] for v in forwarded],
        other_handle_receive_ids=[v['receive_id'] for v in other],
        compound_shapes=[dict(receive_id=v['receive_id'],operations=shape(v)) for v in row['wire']['forwarded']])
    old=row['settled']['dropped'];assert len(old)==1 and not row['settled']['released'] and row['settled']['connection_resets']
    original=old[0];key=manifest_range(original)
    assert original['request']['decoded']['operations'][-1]['stable']==2
    old_result=next(o for o in original['reply']['operations'] if o['op']==38)
    assert old_result['status']==0 and old_result['committed']==2 and old_result['count']==key[2]
    def exact(item):return json.dumps(item['request']['decoded']['operations'],sort_keys=True)
    def retry(item):
        ops=[dict(o) for o in item['request']['decoded']['operations']]
        raw=bytes.fromhex(ops[0]['sequence_hex'])
        assert len(raw)==32 and int.from_bytes(raw[24:28],'big')>=int.from_bytes(raw[20:24],'big')
        ops[0]['sequence_hex']=raw[:24].hex()+'00000000'+raw[28:].hex()
        return json.dumps(ops,sort_keys=True)
    if restarted:
        before=set(row['pre_restart_receive_ids'])
        candidates=[v for v in forwarded if v['receive_id'] not in before]
    else:candidates=forwarded
    assert candidates and all(v['reply']['status'] in (0,10068) for v in candidates)
    retries=[v for v in candidates if v['reply']['status']==10068 and retry(v)==retry(original)]
    successes=[v for v in candidates if v['reply']['status']==0]
    assert successes
    wire=row['wires'][row['relay_role']]['trace']
    def when(item):
        matches=[v['monotonic_ns'] for v in wire if v['direction']=='reply' and v['connection']==item['connection']
                 and v['xid']==item['xid'] and v['decoded']==item['reply']]
        assert matches;return min(matches)
    results=[]
    for item in successes:
        assert item['connection']!=original['connection'] and item['receive_id']!=original['receive_id']
        assert manifest_range(item)==key
        op=item['request']['decoded']['operations'][2]
        reply=next(o for o in item['reply']['operations'] if o['op']==38)
        assert op['stable']==reply['committed']==2 and reply['status']==0 and reply['count']==key[2]
        assert reply['verifier_hex']==old_result['verifier_hex']
        session=retry(item)==retry(original)
        if not session and not restarted:
            assert any(when(r)<when(item) for r in retries) and item['xid']!=original['xid']
        results.append(dict(receive_id=item['receive_id'],session_replay=session,cached_exact=exact(item)==exact(original),
            requested_stable=op['stable'],committed=reply['committed'],stateid_hex=op['stateid_hex'],operations=shape(item),range=list(key)))
        when(item)
    return dict(kind='post_restart_original_intent_write' if restarted else 'live_manifest_replay',scope=scope,
        uncached_retry_receive_ids=[v['receive_id'] for v in retries],
        retry_hint_changed_receive_ids=[v['receive_id'] for v in retries if exact(v)!=exact(original)],successes=results)
