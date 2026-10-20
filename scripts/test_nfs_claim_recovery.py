"""Reject misleading namespace replay evidence; synthetic XDR, no Rust build."""
import copy
import hashlib
import unittest
from nfs_claim_recovery import validate_claim_resend
from nfs_rpc import call, reply
from test_nfs_claim_capability import fixture


def sha(data):return hashlib.sha256(data).hexdigest()


def row(operation):
    state,_,_=fixture(operation); original=copy.deepcopy(state['held'][0])
    def cache(item,hint=0):
        raw=bytearray.fromhex(item['request']['payload_hex'])
        # Fixture SEQUENCE begins immediately after the 56-byte RPC/COMPOUND prefix.
        assert raw[52:56]==bytes.fromhex('00000035')
        raw[80:84]=hint.to_bytes(4,'big');raw[84:88]=(1).to_bytes(4,'big')
        item['request'].update(payload_hex=raw.hex(),sha256=sha(raw),decoded=call(raw))
    cache(original);original['connection']=1
    retry=copy.deepcopy(original);retry.update(connection=2,receive_id=2);cache(retry,1)
    trace=[dict(direction=direction,connection=2,xid=retry['xid'],sha256=digest,monotonic_ns=t)
           for direction,digest,t in (('call',retry['request']['sha256'],1),('reply',retry['reply_sha256'],2))]
    return dict(settled=dict(armed=False,errors=[],released=[],dropped=[original],connection_resets=[1]),
                relay_role='source',wires=dict(source=dict(forwarded=[retry],trace=trace)))


class ClaimRecovery(unittest.TestCase):
    def test_cached_replay_with_resource_hint(self):
        for operation in (11,28):
            proof=validate_claim_resend(row(operation))
            self.assertEqual(proof['kind'],'cached_namespace_session_replay')
            self.assertFalse(proof['successes'][0]['exact_operations'])

    def test_reject_false_replay(self):
        for op in (11,28):
            for failure in ('missing','same_connection','same_receive','missing_trace','reply_hash','request_hash',
                            'wrong_name','wrong_session','uncached','failed_result','released','not_reset','no_cache'):
                r=row(op);wire=r['wires']['source'];item=wire['forwarded'][0]
                if failure=='missing':wire['forwarded']=[]
                elif failure=='same_connection':item['connection']=1
                elif failure=='same_receive':item['receive_id']=1
                elif failure=='missing_trace':wire['trace']=[]
                elif failure=='reply_hash':item['reply_sha256']='wrong'
                elif failure=='request_hash':item['request']['sha256']='wrong'
                elif failure in ('wrong_name','wrong_session','no_cache'):
                    raw=bytearray.fromhex(item['request']['payload_hex'])
                    if failure=='wrong_name':raw=raw.replace(b'data',b'evil',1)
                    elif failure=='wrong_session':raw[56]^=1
                    else:raw[84:88]=bytes(4)
                    item['request'].update(payload_hex=raw.hex(),sha256=sha(raw),decoded=call(raw))
                elif failure=='uncached':item['reply']['status']=10068
                elif failure=='failed_result':item['reply']['operations'][-1]['status']=5
                elif failure=='released':r['settled']['released']=r['settled']['dropped']
                else:r['settled']['connection_resets']=[]
                with self.subTest(op=op,failure=failure),self.assertRaises((AssertionError,ValueError)):
                    validate_claim_resend(r)


if __name__=='__main__':unittest.main()
