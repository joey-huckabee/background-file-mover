"""Reject manifest proof that relies only on timing, filenames or visibility."""
import base64
import copy
import json
import struct
import unittest
import zlib
from nfs_manifest_capability import discover, held_manifest, manifest_data, sha
from test_nfs_io_analysis import u, opaque, request, response, row


def fixture():
    value=dict(version=1,instance_id='instance',job_id='1',generator_id='fixture',submission_id='submission',
        files=[dict(file_id='0',path='nested/data.bin',size_bytes=2097169,algorithm='sha256',sha256=sha(bytes(2097152)+b'0123456789abcdefg'))])
    data=json.dumps(value,separators=(',',':')).encode()
    obj=dict(identity='1:112:1:'+str(len(data)),sha256=sha(data),base64=base64.b64encode(data).decode())
    fd=dict(filesystem='nfs4',mount_id='9',inode=112,path='/manifest',position=0)
    trace=dict(payload_bytes=len(data),events=[dict(syscall=5,args=[7,0,0,0,0,0],enter_ns=1,exit_ns=30,result=0,descriptor=fd),
        dict(syscall=1,args=[7,1000,len(data),0,0,0],enter_ns=40,exit_ns=50,result=len(data),descriptor=fd,
             payload=dict(size=len(data),sha256=sha(data),zlib_base64=base64.b64encode(zlib.compress(data)).decode())),
        dict(syscall=91,args=[7,256,0,0,0,0],enter_ns=100,exit_ns=200,result=0,descriptor=fd)])
    req=request(2,u(38)+bytes(16)+struct.pack('!Q',0)+u(2)+opaque(data))
    ret=u(2,1,0,0,0,0,0)+opaque(b'')+u(2,22,0,38,0,len(data),2)+b'12345678'
    wire=dict(trace_overflow=False,trace_bytes=0,errors=[],trace=[row('call',request(1,u(9,1,(1<<8)|(1<<20))),10),row('reply',response(),20),row('call',req,150),row('reply',ret,170)])
    old=copy.deepcopy(wire['trace'][2]['decoded']);old['operations'].insert(0,dict(op=53))
    held=dict(armed=True,operation=38,held=[dict(xid=2,request=dict(decoded=old),reply=wire['trace'][3]['decoded'])],forwarded=[],released=[],dropped=[],errors=[])
    return obj,trace,dict(source=wire),held


class Evidence(unittest.TestCase):
    def test_positive_exact_manifest_descriptor_and_rpc(self):
        obj,trace,wires,held=fixture()
        manifest_data(obj,'submission')
        proof=discover(trace,wires,'/manifest',obj)
        self.assertEqual(proof['write']['operation']['stable'],2)
        self.assertEqual(proof['commit_requests'],0)
        self.assertEqual(held_manifest(held,obj)['committed'],2)

    def test_missing_identity_timing_buffer_or_success_cannot_qualify(self):
        for mode in ('metadata','inode','path','overlap','buffer','failed_chmod','reply_status','reply_count','reply_missing','overflow'):
            obj,trace,wires,_=fixture();wire=wires['source']
            if mode=='metadata':trace['events']=trace['events'][1:]
            elif mode=='inode':
                for e in trace['events']:e['descriptor']['inode']=113
            elif mode=='path':
                for e in trace['events']:e['descriptor']['path']='/payload'
            elif mode=='overlap':trace['events'][-1]['enter_ns']=151
            elif mode=='buffer':trace['events'][1]['payload']['sha256']='foreign'
            elif mode=='failed_chmod':trace['events'][-1]['result']=-5
            elif mode=='reply_status':wire['trace'][-1]['decoded']['status']=5
            elif mode=='reply_count':wire['trace'][-1]['decoded']['operations'][-1]['count']-=1
            elif mode=='reply_missing':wire['trace'].pop()
            else:wire['trace_overflow']=True
            with self.subTest(mode=mode),self.assertRaises(AssertionError):discover(trace,wires,'/manifest',obj)

    def test_visibility_is_not_matched_held_success(self):
        for mode in ('unarmed','forwarded','wrong_operation','wrong_bytes','wrong_count','weak_reply','wrong_xid','not_success','many_held'):
            obj,_,_,held=fixture();op=held['held'][0]['request']['decoded']['operations'][-1]
            result=held['held'][0]['reply']['operations'][-1]
            if mode=='unarmed':held['armed']=False
            elif mode=='forwarded':held['forwarded']=held['held']
            elif mode=='wrong_operation':held['operation']=5
            elif mode=='wrong_bytes':op['data_sha256']='foreign'
            elif mode=='wrong_count':op['count']-=1
            elif mode=='weak_reply':result['committed']=0
            elif mode=='wrong_xid':held['held'][0]['xid']=3
            elif mode=='not_success':held['held'][0]['reply']['status']=5
            else:held['held'].append(copy.deepcopy(held['held'][0]))
            with self.subTest(mode=mode),self.assertRaises(AssertionError):held_manifest(held,obj)

    def test_server_bytes_must_match_recording_contract(self):
        for mode in ('hash','size','submission','file_hash'):
            obj,_,_,_=fixture();submission='submission'
            if mode=='hash':obj['sha256']='wrong'
            elif mode=='size':obj['identity']='1:112:1:1'
            elif mode=='submission':submission='other'
            else:
                data=json.loads(base64.b64decode(obj['base64']));data['files'][0]['sha256']='wrong'
                raw=json.dumps(data,separators=(',',':')).encode()
                obj.update(base64=base64.b64encode(raw).decode(),sha256=sha(raw),identity='1:112:1:'+str(len(raw)))
            with self.subTest(mode=mode),self.assertRaises(AssertionError):manifest_data(obj,submission)


if __name__=='__main__':unittest.main()
