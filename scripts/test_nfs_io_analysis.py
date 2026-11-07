"""Reject misleading identity/time/payload matches in fixture evidence."""
import base64
import hashlib
import struct
import unittest
import zlib
from nfs_rpc import call, reply
from nfs_io_analysis import identity, analyze

def u(*v):return struct.pack('!'+'I'*len(v),*v)
def opaque(v):return u(len(v))+v+bytes((-len(v))%4)
def request(xid,tail,count=2):return u(xid,0,2,100003,4,1,0,0,0,0)+opaque(b'')+u(1,count)+u(22)+opaque(b'handle')+tail
def response():return u(1,1,0,0,0,0,0)+opaque(b'')+u(2,22,0,9,0,1,(1<<8)|(1<<20))+opaque(struct.pack('!QQQ',68,0,112))
def row(direction,raw,when):return dict(direction=direction,connection=1,xid=struct.unpack('!I',raw[:4])[0],monotonic_ns=when,sha256=hashlib.sha256(raw).hexdigest(),decoded=(call if direction=='call' else reply)(raw),payload_zlib_base64=base64.b64encode(zlib.compress(raw)).decode())

class Evidence(unittest.TestCase):
    def fixture(self):
        data=b'abc';self.event=dict(syscall=1,args=[7,1000,3,0,0,0],enter_ns=100,exit_ns=200,result=3,
            descriptor=dict(filesystem='nfs4',mount_id='9',inode=112,path='/destination/1.part',position=1024),
            payload=dict(size=3,sha256=hashlib.sha256(data).hexdigest(),zlib_base64=base64.b64encode(zlib.compress(data)).decode()))
        self.trace=dict(events=[self.event],payload_bytes=3)
        self.wire=dict(trace_overflow=False,errors=[],trace=[row('call',request(1,u(9,1,(1<<8)|(1<<20))),10),row('reply',response(),20),
            row('call',request(2,u(38)+bytes(16)+struct.pack('!Q',1024)+u(2)+opaque(data)),150)])
    def test_optional_reply_attributes_preserve_default(self):
        default=reply(response());detailed=reply(response(),attributes=True)
        self.assertNotIn('attribute_bitmap',default['operations'][-1])
        self.assertEqual(identity(detailed['operations'][-1]['attribute_bitmap'],detailed['operations'][-1]['attribute_values_hex']),dict(fsid=[68,0],fileid=112))
    def test_identity_prefix_missing_unknown_and_truncation(self):
        self.assertIsNone(identity([1<<20],bytes(8).hex()))
        for length in range(24):
            with self.assertRaises(ValueError):identity([(1<<8)|(1<<20)],bytes(length).hex())
        with self.assertRaises(ValueError):identity([(1<<8)|(1<<12)|(1<<20)],bytes(48).hex())
    def test_positive_anchor_requires_matching_range_bytes_inode_and_time(self):
        self.fixture();result=analyze(self.trace,{'source':self.wire})
        self.assertEqual(len(result['write_matches']),1)
        self.assertEqual(result['rpc_operations'][0]['anchored_descriptor_events'],[0])
    def test_inode_time_range_and_payload_counterexamples(self):
        for kind in ('inode','time','range','payload','failed'):
            self.fixture()
            if kind=='inode':self.event['descriptor']['inode']=113
            if kind=='time':self.event['enter_ns']=151
            if kind=='range':self.event['descriptor']['position']=1025
            if kind=='payload':
                self.event['payload']['zlib_base64']=base64.b64encode(zlib.compress(b'xyz')).decode()
                self.event['payload']['sha256']=hashlib.sha256(b'xyz').hexdigest()
            if kind=='failed':self.event['result']=-5
            with self.subTest(kind=kind):self.assertFalse(analyze(self.trace,{'source':self.wire})['write_matches'])
    def test_unknown_calls_remain_unknown(self):
        self.fixture();self.wire['trace'][-1]['decoded']=None
        result=analyze(self.trace,{'source':self.wire})
        self.assertEqual(result['undecoded_calls'],1);self.assertFalse(result['write_matches'])
    def test_overflow_is_not_absence(self):
        self.fixture();self.wire['trace_overflow']=True
        with self.assertRaises(AssertionError):analyze(self.trace,{'source':self.wire})
    def test_save_restore_handle_prevents_wrong_identity(self):
        self.fixture()
        req=request(1,u(32,22)+opaque(b'other')+u(31,9,1,(1<<8)|(1<<20)),5)
        ret=u(1,1,0,0,0,0,0)+opaque(b'')+u(5,22,0,32,0,22,0,31,0,9,0,1,(1<<8)|(1<<20))+opaque(struct.pack('!QQQ',68,0,112))
        self.wire['trace'][:2]=[row('call',req,10),row('reply',ret,20)]
        result=analyze(self.trace,{'source':self.wire})
        self.assertEqual(len(result['write_matches']),1)
        self.assertIn(hashlib.sha256(b'handle').hexdigest(),result['filehandle_identities'])
        self.assertNotIn(hashlib.sha256(b'other').hexdigest(),result['filehandle_identities'])
    def test_successful_stat_or_open_metadata_anchor_only(self):
        for nr,status in ((5,0),(5,-5),(257,8),(257,-5)):
            self.fixture();self.event.update(syscall=nr,result=status,enter_ns=1,exit_ns=30)
            if nr==257:self.event['returned_descriptor']=self.event['descriptor']
            self.event['pathname']='file' if nr==257 else ''
            matches=analyze(self.trace,{'source':self.wire})['metadata_matches']
            self.assertEqual(bool(matches),status>=0)

if __name__=='__main__':unittest.main()
