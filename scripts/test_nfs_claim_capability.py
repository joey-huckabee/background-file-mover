"""Reject misleading claim capability proofs, using bounded synthetic XDR."""
import copy
import hashlib
import unittest
from nfs_claim_capability import claim_proof
from nfs_rpc import call, reply
from test_nfs_rpc import u, opaque


def fixture(operation):
    name = b'data' if operation == 11 else b'data.bin'
    request = (u(123,0,2,100003,4,1,0,0,0,0)+opaque(b'')+u(1,3,53)+bytes(32)
               +u(22)+opaque(b'fixture handle')+u(operation)+opaque(name))
    response = (u(123,1,0,0,0,0,0)+opaque(b'')+u(3,53,0)+bytes(36)+u(22,0,operation,0,1)+bytes(16))
    item = dict(xid=123,receive_id=1,request=dict(decoded=call(request),payload_hex=request.hex(),sha256=hashlib.sha256(request).hexdigest()),
                reply=reply(response),payload_hex=response.hex(),reply_sha256=hashlib.sha256(response).hexdigest())
    state = dict(armed=True,operation=operation,held=[item],forwarded=[],released=[],dropped=[],errors=[])
    original = dict(device=1,inode=2,links=1,size=3,sha256='fixture hash')
    final = dict(original, links=2 if operation == 11 else 1)
    return state, dict(old=original,final=None), dict(old=final if operation == 11 else None,final=final)


class ClaimCapability(unittest.TestCase):
    def test_both_operations(self):
        for op in (11,28): self.assertEqual(claim_proof(*self.arguments(op))['operation'],op)

    @staticmethod
    def arguments(op):
        state,before,after=fixture(op)
        return state,op,before,after

    def test_false_success_and_aliases(self):
        for op in (11,28):
            for failure in ('unarmed','forwarded','released','dropped','errors','xid','request_hash','reply_hash','raw_request',
                            'raw_reply','decoded_request','decoded_reply','inode','bytes','links','old_alias','initial_alias'):
                state,before,after=fixture(op);item=state['held'][0]
                if failure=='unarmed':state['armed']=False
                elif failure in ('forwarded','released','dropped','errors'):state[failure]=[item]
                elif failure=='xid':item['xid']+=1
                elif failure=='request_hash':item['request']['sha256']='wrong'
                elif failure=='reply_hash':item['reply_sha256']='wrong'
                elif failure=='raw_request':item['request']['payload_hex']='00'
                elif failure=='raw_reply':item['payload_hex']='00'
                elif failure=='decoded_request':item['request']['decoded']['operations'][-1]['name']='wrong'
                elif failure=='decoded_reply':item['reply']['operations'][-1]['status']=5
                elif failure=='inode':after['final']['inode']+=1
                elif failure=='bytes':after['final']['sha256']='wrong'
                elif failure=='links':after['final']['links']=3
                elif failure=='old_alias':after['old']=None if op==11 else dict(after['final'])
                else:before['final']=dict(before['old'])
                with self.subTest(op=op,failure=failure), self.assertRaises((AssertionError,ValueError)):
                    claim_proof(state,op,before,after)

    def test_rehashed_wrong_xid(self):
        for op in (11,28):
            state,before,after=fixture(op);item=state['held'][0]
            raw=bytearray.fromhex(item['payload_hex']);raw[0]^=1
            item.update(payload_hex=raw.hex(),reply_sha256=hashlib.sha256(raw).hexdigest(),reply=reply(raw))
            with self.assertRaises(AssertionError):claim_proof(state,op,before,after)


if __name__=='__main__':unittest.main()
