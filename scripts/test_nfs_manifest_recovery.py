"""Fixture evidence tests: immutable intent and distinct live/restart FILE_SYNC recovery."""
from contextlib import closing
import base64
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from nfs_manifest_recovery import read_intent, validate_intent, validate_manifest_resend
from nfs_manifest_capability import sha
from test_nfs_write_resend import fixture


def recovery():
    row=fixture(2)
    old=row['settled']['dropped'][0]
    old['request']['decoded']['operations'][-1]['stable']=2
    old['reply']['operations'][0]['committed']=2
    row['wire']['forwarded'][0]['request']['decoded']['operations'][-1]['stable']=2
    row['wires']['source']['trace']=row['wires']['source']['trace'][:2]
    return row


class Resend(unittest.TestCase):
    def test_live_retry_and_highest_slot_hint(self):
        row=recovery()
        self.assertEqual(validate_manifest_resend(row)['kind'],'live_manifest_replay')
        op=row['wire']['forwarded'][0]['request']['decoded']['operations'][0]
        op['sequence_hex']=op['sequence_hex'][:48]+'00000002'+op['sequence_hex'][56:]
        self.assertEqual(validate_manifest_resend(row)['retry_hint_changed_receive_ids'],[2])

    def test_cached_success(self):
        row=recovery();item=copy.deepcopy(row['settled']['dropped'][0]);item.update(connection=2,receive_id=3)
        row['wire']['forwarded']=[item]
        row['wires']['source']['trace']=[dict(direction='reply',connection=2,xid=1,decoded=item['reply'],monotonic_ns=20)]
        self.assertTrue(validate_manifest_resend(row)['successes'][0]['cached_exact'])

    def test_restart_write_is_distinct_and_must_be_after_window(self):
        row=recovery();row['wire']['forwarded']=row['wire']['forwarded'][1:];row['pre_restart_receive_ids']=[1,2]
        self.assertEqual(validate_manifest_resend(row,True)['kind'],'post_restart_original_intent_write')
        with self.assertRaises(AssertionError):validate_manifest_resend(row)
        row['pre_restart_receive_ids'].append(3)
        with self.assertRaises(AssertionError):validate_manifest_resend(row,True)

    def test_restart_getattr_compound_is_retained_and_live_scope_stays_strict(self):
        row=recovery();row['wire']['forwarded']=row['wire']['forwarded'][1:];row['pre_restart_receive_ids']=[1,2]
        item=row['wire']['forwarded'][0];item['request']['decoded']['operations'].append(dict(op=9))
        item['reply']['operations'].append(dict(op=9,status=0))
        result=validate_manifest_resend(row,True)
        self.assertEqual(result['successes'][0]['operations'],[53,22,38,9])
        self.assertEqual(result['scope']['compound_shapes'],[dict(receive_id=3,operations=[53,22,38,9])])
        with self.assertRaises(AssertionError):validate_manifest_resend(row)
        for operation in (5,25,38):
            changed=copy.deepcopy(row);changed['wire']['forwarded'][0]['request']['decoded']['operations'][-1]['op']=operation
            with self.subTest(operation=operation),self.assertRaises(AssertionError):validate_manifest_resend(changed,True)

    def test_identity_and_semantic_counterexamples(self):
        modes=('bytes','offset','handle','old_connection','old_receive','missing_retry','weak_request','weak_reply','count','verifier','missing_wire','session','sequence','slot','cache')
        for mode in modes:
            row=recovery();item=row['wire']['forwarded'][1];op=item['request']['decoded']['operations'][-1]
            if mode=='bytes':op['data_sha256']='wrong'
            elif mode=='offset':op['offset']=1
            elif mode=='handle':item['request']['decoded']['operations'][1]['filehandle_sha256']='foreign'
            elif mode=='old_connection':item['connection']=1
            elif mode=='old_receive':item['receive_id']=1
            elif mode=='missing_retry':row['wire']['forwarded']=row['wire']['forwarded'][1:]
            elif mode=='weak_request':op['stable']=0
            elif mode=='weak_reply':item['reply']['operations'][0]['committed']=0
            elif mode=='count':item['reply']['operations'][0]['count']=1
            elif mode=='verifier':item['reply']['operations'][0]['verifier_hex']='different'
            elif mode=='missing_wire':row['wires']['source']['trace']=[]
            else:
                retry=row['wire']['forwarded'][0]['request']['decoded']['operations'][0]
                raw=bytearray.fromhex(retry['sequence_hex']);raw[{'session':0,'sequence':19,'slot':23,'cache':31}[mode]]=1 if mode!='sequence' else 2
                if mode=='slot':raw[27]=2
                retry['sequence_hex']=raw.hex()
            with self.subTest(mode=mode),self.assertRaises(AssertionError):validate_manifest_resend(row)


class Intent(unittest.TestCase):
    def snapshot(self,phase=1):
        body=json.dumps(dict(instance_id='fixture',job_id='1'))
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'db'
            with closing(sqlite3.connect(path)) as db:
                db.executescript('CREATE TABLE metadata(key TEXT,value TEXT); CREATE TABLE manifests(job_id INTEGER,bytes TEXT,sha256 TEXT,phase INTEGER,object_identity TEXT);')
                db.execute('INSERT INTO metadata VALUES(?,?)',('instance_id','fixture'))
                db.execute('INSERT INTO manifests VALUES(?,?,?,?,?)',(1,body,sha(body.encode()),phase,f'1:9:42:1000:{len(body) if phase==4 else 0}:0:0:1'))
                db.commit()
            raw=path.read_bytes()
        files={'jobs.sqlite':dict(base64=base64.b64encode(raw).decode(),sha256=sha(raw),size=len(raw))}
        return dict(files=files,intent=read_intent(files)),dict(base64=base64.b64encode(body.encode()).decode(),sha256=sha(body.encode()),identity=f'9:42:1:{len(body)}')

    def test_phase_and_immutable_original_bytes(self):
        for phase in (1,4):
            snapshot,obj=self.snapshot(phase);validate_intent(snapshot,obj,phase)
            self.assertEqual(read_intent(snapshot['files']),snapshot['intent'])

    def test_invalid_copies_and_identity(self):
        for mode in ('hash','size','path','intent','phase','bytes','inode','owner'):
            snapshot,obj=self.snapshot()
            if mode=='hash':snapshot['files']['jobs.sqlite']['sha256']='wrong'
            elif mode=='size':snapshot['files']['jobs.sqlite']['size']=1
            elif mode=='path':snapshot['files']['../db']=snapshot['files'].pop('jobs.sqlite')
            elif mode=='intent':snapshot['intent']['instance_id']='wrong'
            elif mode=='phase':snapshot['intent']['phase']=4
            elif mode=='bytes':obj['base64']=base64.b64encode(b'wrong').decode()
            elif mode=='inode':obj['identity']='9:43:1:1'
            else:snapshot['intent']['object_identity']='1:9:42:1001:0:0:0:1'
            with self.subTest(mode=mode),self.assertRaises(AssertionError):validate_intent(snapshot,obj,1)


if __name__=='__main__':unittest.main()
