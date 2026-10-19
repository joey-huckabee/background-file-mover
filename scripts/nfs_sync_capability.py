"""Independent actual-fsync RPC discovery and conditional withholding controls."""
import hashlib,json,time,traceback
from nfs_sync_support import build_probe,start_trace,finish_trace,correlate


def write_range(row):
 ops=row['request']['decoded']['operations']
 assert [o['op'] for o in ops]==[53,22,38]
 op=ops[-1]
 return (ops[1]['filehandle_sha256'],op['offset'],op['count'],op['data_sha256'])


def validate_unstable_held(state):
 assert state['armed'] and state['operation']==38 and state['held']
 assert not state['forwarded'] and not state['released'] and not state['dropped'] and not state['errors']
 for row in state['held']:
  write_range(row)
  assert row['xid']==row['request']['decoded']['xid']==row['reply']['xid']
  assert row['request']['decoded']['operations'][-1]['stable']==0 and row['reply']['status']==0
  result=next(o for o in row['reply']['operations'] if o['op']==38)
  assert result['status']==0 and result['committed']==0 and result['count']==write_range(row)[2]


def validate_unstable_resend(row):
 """All lost UNSTABLE ranges need witnessed success on a new connection.

 Preserve exact session replay versus uncached retry/new WRITE distinction.
 If a successful resend is still UNSTABLE, require its subsequent successful
 same-handle/verifier COMMIT. Never treat the old 4 KiB FILE_SYNC control as this.
 """
 dropped=row['settled']['dropped'];forwarded=row['wire']['forwarded']
 assert dropped and forwarded and row['settled']['connection_resets'] and not row['settled']['released']
 assert not {r['connection'] for r in dropped}&{r['connection'] for r in forwarded}
 assert not {r['receive_id'] for r in dropped}&{r['receive_id'] for r in forwarded}
 def exact(r):return json.dumps(r['request']['decoded']['operations'],sort_keys=True)
 def retry_key(r):
  # RFC 8881 section 2.10.6.1: session/slot/sequence identify retries;
  # highest_slotid is a current resource-usage hint, not that identity.
  ops=[dict(o) for o in r['request']['decoded']['operations']]
  sequence=ops[0]['sequence_hex'];raw=bytes.fromhex(sequence)
  assert len(raw)==32 and int.from_bytes(raw[24:28],'big')>=int.from_bytes(raw[20:24],'big')
  ops[0]['sequence_hex']=sequence[:48]+'00000000'+sequence[56:]
  return json.dumps(ops,sort_keys=True)
 originals={exact(r):r for r in dropped}
 sessions={retry_key(r):r for r in dropped}
 ranges={write_range(r) for r in dropped}
 retries=[r for r in forwarded if retry_key(r) in sessions and r['reply']['status']==10068]
 successes=[r for r in forwarded if r['reply']['status']==0]
 assert successes and all(r['reply']['status'] in (0,10068) for r in forwarded)
 retry_ranges={write_range(r) for r in retries}
 assert {write_range(r) for r in successes}==ranges
 commits=[];resends=[]
 wire=row['wires'][row['relay_role']]['trace']
 def received(item):
  times=[r['monotonic_ns'] for r in wire if r['direction']=='reply' and r['connection']==item['connection']
         and r['xid']==item['xid'] and r['decoded']==item['reply']]
  assert times,'forwarded reply missing from captured wire'
  return min(times)
 for item in successes:
  key=write_range(item);op=item['request']['decoded']['operations'][-1]
  result=next(o for o in item['reply']['operations'] if o['op']==38)
  assert result['status']==0 and result['count']==key[2] and 0<=op['stable']<=result['committed']<=2
  for original in dropped:
   assert original['request']['decoded']['operations'][-1]['stable']==0
   original_result=next(o for o in original['reply']['operations'] if o['op']==38)
   assert original_result['committed']==0
   if write_range(original)==key:assert original_result['verifier_hex']==result['verifier_hex']
  cached=exact(item) in originals
  session_replay=retry_key(item) in sessions
  if not session_replay:
   assert key in retry_ranges and item['xid'] not in {r['xid'] for r in dropped}
   assert any(received(r)<received(item) for r in retries if write_range(r)==key)
  if result['committed']==0:
   matches=[]
   for call in wire:
    if call['direction']!='call' or not call['decoded']:continue
    ops=call['decoded']['operations']
    if [o['op'] for o in ops]!=[53,22,5] or ops[1]['filehandle_sha256']!=key[0] or call['monotonic_ns']<received(item):continue
    commit=ops[-1]
    if commit['offset']>key[1] or (commit['count'] and commit['offset']+commit['count']<key[1]+key[2]):continue
    for reply in wire:
     if reply['direction']!='reply' or reply['connection']!=call['connection'] or reply['xid']!=call['xid'] or not reply['decoded']:continue
     if reply['monotonic_ns']<call['monotonic_ns'] or reply['decoded']['status']!=0:continue
     if any(o['op']==5 and o['status']==0 and o['verifier_hex']==result['verifier_hex'] for o in reply['decoded']['operations']):
      matches.append(dict(connection=call['connection'],xid=call['xid'],verifier_hex=result['verifier_hex']))
   assert matches,'UNSTABLE resend lacks matched successful COMMIT'
   commits.extend(matches)
  resends.append(dict(range=list(key),receive_id=item['receive_id'],cached_exact=cached,session_replay=session_replay,
                      requested_stable=op['stable'],committed=result['committed']))
 return dict(kind='unstable_ranges_recovered',uncached_retry_receive_ids=[r['receive_id'] for r in retries],
             retry_hint_changed_receive_ids=[r['receive_id'] for r in retries if exact(r) not in originals],
             successful_ranges=resends,commit_evidence=commits)


def validate_resend(row,operation):
 dropped=row['settled']['dropped'];forwarded=row['wire']['forwarded']
 assert dropped and forwarded and row['settled']['connection_resets'] and not row['settled']['released']
 assert not {r['connection'] for r in dropped}&{r['connection'] for r in forwarded}
 assert not {r['receive_id'] for r in dropped}&{r['receive_id'] for r in forwarded}
 def exact(r):return json.dumps(r['request']['decoded']['operations'],sort_keys=True)
 identities={exact(r) for r in dropped}
 if all(exact(r) in identities and r['reply']['status']==0 for r in forwarded):
  return dict(kind='cached_exact_replay')
 # WRITE with cachethis=false may get RETRY_UNCACHED_REP, then the native
 # client reissues the same idempotent data range with current open state.
 assert operation==38
 retries=[r for r in forwarded if exact(r) in identities and r['reply']['status']==10068]
 successes=[r for r in forwarded if r['reply']['status']==0]
 assert retries and successes
 def semantic(r):
  ops=r['request']['decoded']['operations']
  assert [o['op'] for o in ops]==[53,22,38]
  return (ops[1]['filehandle_sha256'],*[ops[2][k] for k in ('offset','stable','count','data_sha256')])
 original={semantic(r) for r in dropped}
 for r in successes:
  assert semantic(r) in original
  assert any(o['op']==38 and o['status']==0 and o['count']==r['request']['decoded']['operations'][-1]['count'] and o['committed']==2 for o in r['reply']['operations'])
  assert exact(r) not in identities and r['xid'] not in {v['xid'] for v in dropped}
 assert all(r['reply']['status'] in (0,10068) for r in forwarded)
 return dict(kind='uncached_reply_then_semantic_write_resend',uncached_retry_receive_ids=[r['receive_id'] for r in retries],successful_resend_receive_ids=[r['receive_id'] for r in successes])


def qualify(relay,endpoints,run,execute,spawn,output,client,containers,config,result):
 result.update(passed=False,observations=[],withholding=[],scope='OS-only sync discovery; buffered controls do not qualify noac mover behavior')
 result['probe']=build_probe(run,output,client,containers,config)
 mount=endpoints.mounts['destination'];server=endpoints.servers['destination']
 result['original_mounts']=execute('cat /proc/mounts').stdout.splitlines()
 execute('mkdir -m 700 /tmp/sync-probes','1000:1000')
 count=0
 def probe(mode,label,hold=None):
  nonlocal count
  count+=1;base='/tmp/sync-probes/'+str(count);target=mount+'/sync-'+str(count)
  if mode=='directory':execute('mkdir -m 700 '+target,'1000:1000')
  command=f'/tmp/nfs-sync-probe {mode} {target} {base}.ready {base}.go'
  process=spawn('exec '+command,'sync-'+label)
  observer=None;row=dict(label=label,mode=mode,passed=False,target=target)
  try:
   for _ in range(30):
    ready=execute('cat '+base+'.ready','1000:1000',check=False)
    if ready.returncode==0:break
    assert process.poll() is None;time.sleep(.1)
   else:raise AssertionError('sync probe not ready')
   pid,fd=map(int,ready.stdout.split());row.update(pid=pid,fd=fd)
   observer=start_trace(run,client,pid,containers,config) if hold is None else None
   relay.command('observe')
   if hold is not None:relay.command('arm',None,hold)
   execute('touch '+base+'.go','1000:1000')
   if hold is not None:
    held=relay.await_held();row['held']=held
    raw=execute(f'cat /proc/{pid}/syscall').stdout.strip();row['native_syscall']=raw
    assert raw.split()[0]=='74' and int(raw.split()[1],16)==fd,raw
    assert execute(f'cat /proc/{pid}/stat').stdout.rsplit(') ',1)[1].split()[0]=='D'
    row['pending_fd_path']=execute(f'readlink /proc/{pid}/fd/{fd}').stdout.strip();assert row['pending_fd_path']==target
    remote=target.replace(mount,'/exports/death-destination',1)
    content=run(['exec',server,'sha256sum',remote]).stdout.split()[0]
    assert content==hashlib.sha256(b'S'*4096).hexdigest();row['server_sha256_while_withheld']=content
    row['server_identity_while_withheld']=run(['exec',server,'stat','-c','%d:%i:%h:%s',remote]).stdout.strip()
    row['server_threads']={role:run(['exec',value,'cat','/proc/fs/nfsd/threads']).stdout.strip() for role,value in endpoints.servers.items()};assert set(row['server_threads'].values())=={'2'}
    row['before_release_or_drop']=relay.await_held()
    row['settled']=relay.command('drop' if label.endswith('drop') else 'release')
   assert process.wait(timeout=30)==0
   row['wire']=relay.command('stop_observe')
   if observer:row['syscalls']=correlate(finish_trace(run,observer),row['wire'])
   text=(output/('sync-'+label+'.log')).read_text(encoding='utf-8');assert 'fsync returned 0' in text;row['probe_output']=text
   if hold is not None and label.endswith('drop'):
    row['resend_validation']=validate_resend(row,hold)
   if hold is not None:
    row['server_identity_after']=run(['exec',server,'stat','-c','%d:%i:%h:%s',remote]).stdout.strip()
    row['server_sha256_after']=run(['exec',server,'sha256sum',remote]).stdout.split()[0]
    assert row['server_identity_after']==row['server_identity_while_withheld']
    assert row['server_sha256_after']==row['server_sha256_while_withheld']
   row['passed']=True;print('NFS synchronization capability '+label+': PASS',flush=True)
   return row
  except Exception as error:
   row.update(error=str(error),traceback=traceback.format_exc());result.setdefault('failed_probes',[]).append(row);raise
  finally:
   relay.release()
   if process.poll() is None:
    execute('touch '+base+'.go','1000:1000',check=False)
    process.wait(timeout=30)
 for mode in ('clean','dirty','directory'):result['observations'].append(probe(mode,'noac-'+mode))
 # Different profile, explicitly separated from the existing mover fixture.
 run(['exec',client,'umount',mount])
 address=endpoints.report['servers']['destination']['ip']
 options=f'addr={address},vers=4.1,proto=tcp,port=2049,hard,timeo=10,retrans=1,ac,async'
 run(['exec',client,'mount','-i','-t','nfs4','-o',options,address+':/death-destination',mount])
 result['buffered_mounts']=execute('cat /proc/mounts').stdout.splitlines()
 lines=[line for line in result['buffered_mounts'] if line.split()[1]==mount];assert len(lines)==1
 flags=lines[0].split()[3].split(',');assert 'sync' not in flags and 'noac' not in flags
 discovered=probe('dirty','buffered-dirty');result['observations'].append(discovered)
 candidates=[op['op'] for sync in discovered['syscalls']['syncs'] for call in sync['rpc_calls'] if call['decoded'] for op in call['decoded']['operations'] if op['op'] in (5,38)]
 result['observed_sync_operations']=sorted(set(candidates))
 if candidates:
  operation=5 if 5 in candidates else 38
  for mode in ('release','drop'):result['withholding'].append(probe('dirty','buffered-'+mode,operation))
  result['withholding_available']=True
 else:
  result['withholding_available']=False;result['limitation']='No decodable COMMIT/WRITE inside the observed buffered fsync; no reply-withholding qualification claimed.'
 result['passed']=True
