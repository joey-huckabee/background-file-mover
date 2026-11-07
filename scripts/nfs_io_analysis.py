"""Bounded fixture identity/interval analysis; never production effect authority.

RFC 8881 sections 5.6/5.8: attributes ordered by bitmap bit, fsid=8/fileid=20.
https://www.rfc-editor.org/rfc/rfc8881.html#section-5.8
"""
import base64
import hashlib
import struct
import zlib
from nfs_rpc import Xdr, reply


def identity(words, values):
    """Decode only the defined attribute prefix through fileid, fail closed."""
    bits=[i*32+j for i,w in enumerate(words) for j in range(32) if w & (1<<j)]
    if 8 not in bits or 20 not in bits:
        return None
    x=Xdr(bytes.fromhex(values));result={}
    for bit in bits:
        if bit>20:break
        if bit==0:x.bitmap()
        elif bit==8:result['fsid']=list(struct.unpack('!QQ',x.take(16)))
        elif bit==20:result['fileid']=struct.unpack('!Q',x.take(8))[0]
        elif bit in (3,4):x.take(8)
        elif bit==19:x.opaque()
        elif bit in (1,2,5,6,7,9,10,11,13,14,15,16,17,18):x.take(4)
        else:raise ValueError('unsupported identity-prefix attribute '+str(bit))
    return result


def analyze(trace, wires):
    assert len(trace['events'])<=8192 and trace['payload_bytes']<=8*1048576
    events=trace['events'];identities={};rpc=[];unknown=0;errors=[];getattrs=[]
    for role,wire in wires.items():
        assert not wire['trace_overflow'] and not wire['errors']
        pending={}
        for row in wire['trace']:
            key=(row['connection'],row['xid'])
            if row['direction']=='call':
                pending[key]=row
                if row['decoded'] is None:unknown+=1
                else:
                    fh=saved=None
                    for op in row['decoded']['operations']:
                        if op['op']==22:fh=op['filehandle_sha256']
                        elif op['op']==32:saved=fh
                        elif op['op']==31:fh=saved
                        elif op['op'] in (15,16,24):fh=None
                        if op['op'] in (5,38):
                            rpc.append(dict(relay_role=role,connection=row['connection'],xid=row['xid'],
                                monotonic_ns=row['monotonic_ns'],request_sha256=row['sha256'],
                                filehandle_sha256=fh,operation=op))
            elif key in pending:
                request=pending.pop(key)
                if request['decoded'] is None:continue
                try:decoded=reply(zlib.decompress(base64.b64decode(row['payload_zlib_base64'])),attributes=True)
                except ValueError:continue
                fh=saved=None
                for arg,ret in zip(request['decoded']['operations'],decoded['operations']):
                    if arg['op']!=ret['op'] or ret['status']!=0:break
                    if arg['op']==22:fh=arg['filehandle_sha256']
                    elif arg['op']==32:saved=fh
                    elif arg['op']==31:fh=saved
                    elif arg['op'] in (15,16,24):fh=None
                    elif arg['op']==10:fh=ret['filehandle_sha256']
                    elif arg['op']==9 and fh:
                        try:value=identity(ret['attribute_bitmap'],ret['attribute_values_hex'])
                        except ValueError as e:
                            errors.append(dict(reply_sha256=row['sha256'],error=str(e)));continue
                        if value is None:continue
                        if fh in identities:assert identities[fh]['identity']==value,'conflicting filehandle identity'
                        else:identities[fh]=dict(identity=value,request_sha256=request['sha256'],reply_sha256=row['sha256'])
                        getattrs.append(dict(filehandle_sha256=fh,identity=value,request_sha256=request['sha256'],
                            enter_ns=request['monotonic_ns'],exit_ns=row['monotonic_ns']))
    anchors={};matches=[];metadata_matches=[]
    # Metadata evidence is distinct from byte/range proof. Require both ends
    # of a GETATTR pair inside one descriptor-relative stat syscall, matching
    # fileid and an unambiguous filehandle for that descriptor object.
    for index,event in enumerate(events):
        opening=event['syscall'] in (2,257,437)
        fd=event.get('returned_descriptor') if opening else event.get('descriptor')
        if not fd or fd['filesystem'] not in ('nfs','nfs4'):continue
        if opening:
            if event['result']<0:continue
        elif event['syscall'] not in (5,262,332) or event['result']!=0:continue
        if event['syscall'] in (262,332) and event.get('pathname')!='':continue
        candidates=[g for g in getattrs if event['enter_ns']<=g['enter_ns']<=g['exit_ns']<=event['exit_ns']
                    and g['identity']['fileid']==fd['inode']]
        handles={g['filehandle_sha256'] for g in candidates}
        if len(handles)!=1:continue
        fh=next(iter(handles));key=fd['mount_id']+':'+str(fd['inode'])
        assert key not in anchors or anchors[key]==fh,'ambiguous metadata descriptor anchor'
        anchors[key]=fh
        metadata_matches.append(dict(event_index=index,filehandle_sha256=fh,mount_id=fd['mount_id'],inode=fd['inode'],path=fd['path'],
            fsid=identities[fh]['identity']['fsid'],getattr_request_sha256=candidates[0]['request_sha256'],kind='getattr_pair_inode_and_descriptor_open_or_stat_interval'))
    for index,event in enumerate(events):
        assert event['enter_ns']<=event['exit_ns']
        fd=event.get('descriptor')
        if not fd or fd['filesystem'] not in ('nfs','nfs4'):continue
        for request in rpc:
            if request['operation']['op']!=38 or event['syscall'] not in (1,18) or event['result']<=0:continue
            if not event['enter_ns']<=request['monotonic_ns']<=event['exit_ns']:continue
            fh=request['filehandle_sha256'];ident=identities.get(fh)
            if not ident or ident['identity']['fileid']!=fd['inode']:continue
            data=zlib.decompress(base64.b64decode(event['payload']['zlib_base64']))
            assert len(data)==event['payload']['size'] and hashlib.sha256(data).hexdigest()==event['payload']['sha256']
            offset=event['args'][3] if event['syscall']==18 else fd['position']
            op=request['operation'];start=op['offset']-offset
            if start<0 or start+op['count']>event['result']:continue
            if hashlib.sha256(data[start:start+op['count']]).hexdigest()!=op['data_sha256']:continue
            key=fd['mount_id']+':'+str(fd['inode'])
            assert key not in anchors or anchors[key]==fh,'ambiguous descriptor anchor'
            anchors[key]=fh
            matches.append(dict(event_index=index,request_sha256=request['request_sha256'],filehandle_sha256=fh,
                inode=fd['inode'],mount_id=fd['mount_id'],path=fd['path'],fsid=ident['identity']['fsid'],kind='write_bytes_range_inode_and_interval'))
    for request in rpc:
        request['overlapping_events']=[index for index,e in enumerate(events)
            if e['enter_ns']<=request['monotonic_ns']<=e['exit_ns']]
        request['anchored_descriptor_events']=[]
        for index in request['overlapping_events']:
            fd=events[index].get('descriptor')
            if fd and anchors.get(fd['mount_id']+':'+str(fd['inode']))==request['filehandle_sha256']:
                request['anchored_descriptor_events'].append(index)
    return dict(filehandle_identities=identities,descriptor_anchors=anchors,write_matches=matches,metadata_matches=metadata_matches,rpc_operations=rpc,
                undecoded_calls=unknown,identity_prefix_errors=errors,
                limitation='Interval correlation and fixture-local identity/payload anchors do not prove unique kernel causality or NAS durability. Unmatched/unknown operations stay explicit.')
