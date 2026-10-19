"""Reject incomplete/misidentified/unsynchronized UNSTABLE resend evidence."""
import copy
import struct
import unittest
from nfs_sync_capability import validate_unstable_held, validate_unstable_resend


def request(xid, sequence=1, offset=0, stable=0):
    return dict(xid=xid,operations=[dict(op=53,sequence_hex=struct.pack('!16sIIII',b'S'*16,sequence,0,0,0).hex()),dict(op=22,filehandle_sha256='handle'),
        dict(op=38,offset=offset,count=17,stable=stable,data_sha256='bytes',stateid_hex=str(sequence))])


def reply(xid, status=0, committed=0):
    return dict(xid=xid,status=status,operations=[dict(op=38,status=0,count=17,committed=committed,verifier_hex='boot')]
                if status==0 else [dict(op=53,status=status)])


def record(xid,connection,receive,sequence=1,offset=0,stable=0,status=0,committed=0):
    return dict(xid=xid,connection=connection,receive_id=receive,
        request=dict(decoded=request(xid,sequence,offset,stable)),reply=reply(xid,status,committed))


def fixture(stable=0):
    old=record(1,1,1)
    retry=record(1,2,2,status=10068)
    new=record(2,2,3,sequence=2,stable=stable,committed=stable)
    trace=[dict(direction='reply',connection=2,xid=r['xid'],decoded=r['reply'],monotonic_ns=t)
           for r,t in ((retry,10),(new,20))]
    trace += [dict(direction='call',connection=2,xid=3,monotonic_ns=30,decoded=dict(operations=[
        dict(op=53),dict(op=22,filehandle_sha256='handle'),dict(op=5,offset=0,count=0)])),
        dict(direction='reply',connection=2,xid=3,monotonic_ns=40,decoded=dict(status=0,operations=[
            dict(op=5,status=0,verifier_hex='boot')]))]
    return dict(settled=dict(dropped=[old],released=[],connection_resets=[1]),
        wire=dict(forwarded=[retry,new]),relay_role='source',wires=dict(source=dict(trace=trace)))


class Evidence(unittest.TestCase):
    def test_unstable_resend_needs_later_successful_commit(self):
        result=validate_unstable_resend(fixture())
        self.assertTrue(result['commit_evidence'])
        self.assertEqual(result['successful_ranges'][0]['committed'],0)

    def test_file_sync_resend_is_recorded_separately(self):
        value=fixture(2);value['wires']['source']['trace']=value['wires']['source']['trace'][:2]
        result=validate_unstable_resend(value)
        self.assertEqual(result['successful_ranges'][0]['requested_stable'],2)
        self.assertFalse(result['commit_evidence'])

    def test_cached_exact_session_replay(self):
        value=fixture();item=copy.deepcopy(value['settled']['dropped'][0]);item.update(connection=2,receive_id=3)
        value['wire']['forwarded']=[item]
        value['wires']['source']['trace'][1].update(xid=1,decoded=item['reply'])
        self.assertTrue(validate_unstable_resend(value)['successful_ranges'][0]['cached_exact'])

    def test_retry_highest_slot_hint_can_change(self):
        value=fixture();op=value['wire']['forwarded'][0]['request']['decoded']['operations'][0]
        op['sequence_hex']=op['sequence_hex'][:48]+'00000002'+op['sequence_hex'][56:]
        result=validate_unstable_resend(value)
        self.assertEqual(result['retry_hint_changed_receive_ids'],[2])

    def test_retry_identity_cannot_change(self):
        for start in (0,32,40,56):
            value=fixture();op=value['wire']['forwarded'][0]['request']['decoded']['operations'][0]
            end=2 if start==0 else start+8
            replacement='ff' if start==0 else '00000002' if start==32 else '00000001'
            op['sequence_hex']=op['sequence_hex'][:start]+replacement+op['sequence_hex'][end:]
            if start==40:op['sequence_hex']=op['sequence_hex'][:48]+'00000002'+op['sequence_hex'][56:]
            with self.subTest(field=start),self.assertRaises(AssertionError):validate_unstable_resend(value)

    def test_semantic_counterexamples(self):
        for mode in ('wrong_bytes','wrong_range','wrong_handle','missing_range','old_connection',
                     'missing_retry','old_receive','weak_reply','changed_verifier'):
            value=fixture();item=value['wire']['forwarded'][1];op=item['request']['decoded']['operations'][-1]
            if mode=='wrong_bytes':op['data_sha256']='other'
            elif mode=='wrong_range':op['offset']=19
            elif mode=='wrong_handle':item['request']['decoded']['operations'][1]['filehandle_sha256']='foreign'
            elif mode=='missing_range':value['settled']['dropped'].append(record(9,1,9,offset=99))
            elif mode=='old_connection':item['connection']=1
            elif mode=='missing_retry':value['wire']['forwarded']=value['wire']['forwarded'][1:]
            elif mode=='old_receive':item['receive_id']=1
            elif mode=='weak_reply':op['stable']=2
            else:item['reply']['operations'][0]['verifier_hex']='other'
            with self.subTest(mode=mode),self.assertRaises(AssertionError):validate_unstable_resend(value)

    def test_commit_counterexamples(self):
        for mode in ('missing','before_write_reply','foreign_handle','foreign_verifier','too_short','error'):
            value=fixture();wire=value['wires']['source']['trace']
            if mode=='missing':del wire[2:]
            elif mode=='before_write_reply':wire[2]['monotonic_ns']=15
            elif mode=='foreign_handle':wire[2]['decoded']['operations'][1]['filehandle_sha256']='foreign'
            elif mode=='foreign_verifier':wire[3]['decoded']['operations'][0]['verifier_hex']='other'
            elif mode=='too_short':wire[2]['decoded']['operations'][-1]['count']=1
            else:wire[3]['decoded']['status']=5
            with self.subTest(mode=mode),self.assertRaises(AssertionError):validate_unstable_resend(value)

    def test_held_file_sync_is_not_unstable(self):
        state=dict(armed=True,operation=38,held=[record(1,1,1)],forwarded=[],released=[],dropped=[],errors=[])
        validate_unstable_held(state)
        for mode in ('request','reply'):
            value=copy.deepcopy(state)
            if mode=='request':value['held'][0]['request']['decoded']['operations'][-1]['stable']=2
            else:value['held'][0]['reply']['operations'][0]['committed']=2
            with self.subTest(mode=mode),self.assertRaises(AssertionError):validate_unstable_held(value)


if __name__=='__main__':unittest.main()
