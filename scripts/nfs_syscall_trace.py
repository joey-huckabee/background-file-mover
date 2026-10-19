"""Bounded external fixture tracer; no service code or package dependency."""
import ctypes,json,os,signal,struct,sys,time,traceback
pid=int(sys.argv[1]);libc=ctypes.CDLL(None,use_errno=True)
libc.ptrace.restype=ctypes.c_long
result=dict(passed=False,pid=pid,syncs=[],signals=[],syscall_stops=0,scope='modern-kernel external ptrace observer')
expected_exit=sys.argv[2] if len(sys.argv)>2 else 'zero'
assert expected_exit in ('zero','supervised-delivery')
result['expected_exit']=expected_exit
attached=False;stopped=False;current=None;deadline=time.monotonic()+180

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

try:
 ptrace(16);attached=True;status=wait();assert os.WIFSTOPPED(status)
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
    nr,fd=struct.unpack_from('<QQ',data.raw,24)
    current=None
    if nr in (74,75):
     path='/proc/'+str(pid)+'/fd/'+str(fd)
     # proc fdinfo/mountinfo are local kernel observations. Never stat the NFS
     # target: an observation must not trigger revalidation/writeback before sync.
     info=dict(line.split(':',1) for line in open('/proc/'+str(pid)+'/fdinfo/'+str(fd)) if ':' in line)
     mid=info['mnt_id'].strip()
     mounts=[line.split() for line in open('/proc/'+str(pid)+'/mountinfo')]
     mount=next(line for line in mounts if line[0]==mid)
     major,minor=map(int,mount[2].split(':'))
     current=dict(syscall=nr,fd=fd,path=os.readlink(path),device=os.makedev(major,minor),inode=int(info['ino']),mount_id=mid,
                  enter_ns=time.monotonic_ns())
     result['syncs'].append(current)
   elif kind==2 and current is not None:
    current.update(exit_ns=time.monotonic_ns(),result=struct.unpack_from('<q',data.raw,24)[0]);current=None
  elif sig not in (signal.SIGSTOP,signal.SIGTRAP):
   result['signals'].append(sig);deliver=sig
  ptrace(24,0,deliver);stopped=False
 assert result['syncs']
 assert result['exit_status']==0 or (expected_exit=='supervised-delivery' and result['exit_status']==9)
 result['completion']='normal_exit' if result['exit_status']==0 else 'supervised_retirement_requires_committed_receipt'
 assert all(s.get('result')==0 for s in result['syncs'])
 result['passed']=True
except Exception as error:
 result.update(error=str(error),traceback=traceback.format_exc())
finally:
 if attached:
  try:
   if not stopped:
    os.kill(pid,signal.SIGSTOP);deadline=time.monotonic()+5;wait()
   ptrace(17)
  except Exception as error:result['cleanup_error']=str(error)
 print(json.dumps(result),flush=True)
 sys.exit(0 if result['passed'] else 1)
