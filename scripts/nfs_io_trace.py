"""Bounded external fixture tracer; no service code or package dependency."""
import base64,ctypes,hashlib,json,os,signal,struct,sys,time,traceback,zlib
pid=int(sys.argv[1]);libc=ctypes.CDLL(None,use_errno=True)
libc.ptrace.restype=ctypes.c_long
result=dict(passed=False,pid=pid,syncs=[],signals=[],syscall_stops=0,scope='modern-kernel external ptrace I/O observer',events=[],payload_bytes=0,event_limit=8192,payload_limit=8*1048576)
expected_exit=sys.argv[2] if len(sys.argv)>2 else 'zero'
assert expected_exit in ('zero','supervised-delivery','coordinator-death')
result['expected_exit']=expected_exit
attached=False;stopped=False;current=None;deadline=time.monotonic()+180
gate=json.loads(sys.argv[3]) if len(sys.argv)>3 else None
gated=None
if gate:
 assert set(gate)=={'path'} and gate['path'].startswith(('/tmp/recovery-destination/','/tmp/recovery-source/'))
 os.mkdir('/tmp/sync-gate');result['gate']=dict(path=gate['path'],entry=None,exit=None)

def gate_wait(stage,row):
 # Local observer rendezvous only. No worker NFS access or syscall substitution.
 value=dict(row);value['observed_ns']=time.monotonic_ns()
 with open('/tmp/sync-gate/'+stage+'.next','w') as f:json.dump(value,f)
 os.rename('/tmp/sync-gate/'+stage+'.next','/tmp/sync-gate/'+stage+'.json')
 until=min(deadline,time.monotonic()+60)
 while time.monotonic()<until:
  if os.path.exists('/tmp/sync-gate/'+stage+'-go'):return value
  time.sleep(.01)
 raise TimeoutError('external sync gate '+stage+' deadline')

def ptrace(request,addr=0,data=0):
 value=libc.ptrace(request,pid,ctypes.c_void_p(addr),ctypes.c_void_p(data))
 if value==-1:raise OSError(ctypes.get_errno(),os.strerror(ctypes.get_errno()))
 return value

def wait():
 global stopped
 while time.monotonic()<deadline:
  target,status=os.waitpid(pid,os.WNOHANG)
  if target:
   stopped=os.WIFSTOPPED(status);return status
  time.sleep(.001)
 raise TimeoutError('bounded syscall observer deadline')

# Syscall numbers: Linux v6.6 arch/x86/entry/syscalls/syscall_64.tbl.
# Read only local proc state/memory. Never stat/read a target NFS pathname.
names={0:'read',1:'write',2:'open',3:'close',5:'fstat',8:'lseek',17:'pread64',18:'pwrite64',19:'readv',20:'writev',32:'dup',33:'dup2',72:'fcntl',74:'fsync',75:'fdatasync',91:'fchmod',138:'fstatfs',257:'openat',262:'newfstatat',263:'unlinkat',264:'renameat',265:'linkat',268:'fchmodat',292:'dup3',316:'renameat2',332:'statx',437:'openat2',452:'fchmodat2'}
mounts={line.split()[0]:line.split(' - ',1)[1].split()[0] for line in open('/proc/'+str(pid)+'/mountinfo')}
mem=None

def descriptor(fd):
 if fd>0x7fffffff:return None
 try:
  info=dict(line.split(':',1) for line in open('/proc/'+str(pid)+'/fdinfo/'+str(fd)) if ':' in line)
  mid=info['mnt_id'].strip()
  return dict(fd=fd,path=os.readlink('/proc/'+str(pid)+'/fd/'+str(fd)),mount_id=mid,inode=int(info['ino']),
              flags=int(info['flags'],8),position=int(info['pos']),filesystem=mounts.get(mid,'unknown'))
 except FileNotFoundError:return None

def memory(addr,size):
 data=os.pread(mem,size,addr)
 if len(data)!=size:raise ValueError('short worker-memory observation')
 return data

def string(addr):
 data=bytearray()
 while len(data)<4096:
  part=os.pread(mem,min(256,4096-len(data),4096-(addr%4096)),addr)
  if not part:raise ValueError('short pathname observation')
  if b'\0' in part:return (data+part.split(b'\0',1)[0]).decode('utf-8')
  data.extend(part);addr+=len(part)
 raise ValueError('pathname observation bound')

def entry(nr,args):
 if nr not in names:return None
 row=dict(syscall=nr,name=names[nr],args=list(args),descriptor=descriptor(args[0]) if nr!=2 else None)
 if nr in (2,257,262,263,264,265,268,316,332,437,452):
  row['pathname']=string(args[0] if nr==2 else args[1])
 if nr in (264,265,316):
  row['second_directory']=descriptor(args[2]);row['second_pathname']=string(args[3])
 if nr in (1,18) and row['descriptor'] and row['descriptor']['filesystem'] in ('nfs','nfs4'):
  count=args[2];assert count<=1048576 and result['payload_bytes']+count<=result['payload_limit']
  data=memory(args[1],count);result['payload_bytes']+=count
  row['payload']=dict(size=count,sha256=hashlib.sha256(data).hexdigest(),zlib_base64=base64.b64encode(zlib.compress(data)).decode())
 row['enter_ns']=time.monotonic_ns()
 return row

try:
 ptrace(16);attached=True;status=wait();assert os.WIFSTOPPED(status)
 mem=os.open('/proc/'+str(pid)+'/mem',os.O_RDONLY)
 ptrace(0x4200,0,1)  # PTRACE_O_TRACESYSGOOD
 open('/tmp/trace-ready','x').close()
 ptrace(24);stopped=False
 while True:
  status=wait()
  if os.WIFEXITED(status) or os.WIFSIGNALED(status):
   result['exit_status']=status;attached=False;break
  sig=os.WSTOPSIG(status);deliver=0
  if sig==(signal.SIGTRAP|0x80):
   data=ctypes.create_string_buffer(128);size=ptrace(0x420e,128,ctypes.addressof(data))
   assert size>=24 and struct.unpack_from('<I',data.raw,4)[0]==0xc000003e
   kind=data.raw[0];result['syscall_stops']+=1
   if kind==1:
    nr=struct.unpack_from('<Q',data.raw,24)[0];args=struct.unpack_from('<6Q',data.raw,32)
    current=entry(nr,args)
    if current is not None:
     assert len(result['events'])<result['event_limit'];result['events'].append(current)
     if nr in (74,75):
      fd=current['descriptor'];assert fd is not None
      current.update(fd=fd['fd'],path=fd['path'],inode=fd['inode'],mount_id=fd['mount_id'])
      result['syncs'].append(current)
      if gate and gated is None and nr==74 and fd['path']==gate['path']:
       gated=current;result['gate']['entry']=gate_wait('entry',current)
       # Exclude the artificial ptrace hold from the actual syscall/RPC interval.
       current['enter_ns']=time.monotonic_ns()
   elif kind==2 and current is not None:
    current.update(exit_ns=time.monotonic_ns(),result=struct.unpack_from('<q',data.raw,24)[0])
    if current['syscall'] in (2,32,33,257,292,437) and current['result']>=0:
     current['returned_descriptor']=descriptor(current['result'])
    if current['descriptor'] and current['syscall']!=3:
     current['descriptor_after']=descriptor(current['descriptor']['fd'])
    if gate and current is gated:result['gate']['exit']=gate_wait('exit',current)
    current=None
  elif sig not in (signal.SIGSTOP,signal.SIGTRAP):
   result['signals'].append(sig);deliver=sig
  ptrace(24,0,deliver);stopped=False
 assert result['syncs'] or expected_exit=='coordinator-death'
 if expected_exit=='coordinator-death':assert result['exit_status'] in (9,256)
 else:assert result['exit_status']==0 or (expected_exit=='supervised-delivery' and result['exit_status']==9)
 result['completion']='orphan_exit_requires_independent_remote_reconciliation' if expected_exit=='coordinator-death' else 'normal_exit' if result['exit_status']==0 else 'supervised_retirement_requires_committed_receipt'
 assert all(s.get('result')==0 for s in result['syncs'])
 if gate:assert result['gate']['entry'] and result['gate']['exit']
 result['passed']=True
except Exception as error:
 result.update(error=str(error),traceback=traceback.format_exc())
finally:
 if mem is not None:os.close(mem)
 if attached:
  try:
   if not stopped:
    os.kill(pid,signal.SIGSTOP);deadline=time.monotonic()+5;wait()
   ptrace(17)
  except Exception as error:result['cleanup_error']=str(error)
 print(json.dumps(result),flush=True)
 sys.exit(0 if result['passed'] else 1)
