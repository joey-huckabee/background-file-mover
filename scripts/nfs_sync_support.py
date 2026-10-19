"""Private fixture C probe and external ptrace observer provisioning."""
import hashlib,importlib.util,json,time
from pathlib import Path


def build_probe(run,output,client,containers,config):
 source=Path(__file__).with_name('nfs_sync_probe.c')
 builder=run(['create','--network','none','--cap-drop','all','--entrypoint','/bin/sh',config['builder'],'-c','exec sleep infinity']).stdout.strip();containers.append(builder)
 run(['start',builder]);run(['cp',str(source),builder+':/tmp/nfs_sync_probe.c'])
 run(['exec','--user','1000:1000','--env','ZIG_GLOBAL_CACHE_DIR=/tmp/zig-global','--env','ZIG_LOCAL_CACHE_DIR=/tmp/zig-local',builder,'zig','cc','-target','x86_64-linux-gnu.2.22','-O2','-Wall','-Wextra','-Werror','/tmp/nfs_sync_probe.c','-o','/tmp/nfs-sync-probe'])
 elf=run(['exec',builder,'readelf','-W','-h','-l','-d','--dyn-syms','/tmp/nfs-sync-probe']).stdout
 spec=importlib.util.spec_from_file_location('sles_gate',source.with_name('check-rust-sles.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 audit=module.audit(elf);path=output/'nfs-sync-probe';run(['cp',builder+':/tmp/nfs-sync-probe',str(path)]);run(['cp',str(path),client+':/tmp/nfs-sync-probe'])
 run(['exec',client,'chmod','755','/tmp/nfs-sync-probe'])
 return dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),elf=audit,compiler=run(['exec',builder,'zig','version']).stdout.strip(),scope='fixture-only non-Rust OS probe, not a mover executable')


def start_trace(run,client,pid,containers,config,expected_exit='zero',io=False):
 name='nfs_io_trace.py' if io else 'nfs_syscall_trace.py'
 observer=run(['create','--network','none','--pid','container:'+client,'--cap-drop','all','--cap-add','SYS_PTRACE','--cap-add','DAC_READ_SEARCH','--security-opt','no-new-privileges','--entrypoint','/usr/bin/python3',config['builder'],'/tmp/'+name,str(pid),expected_exit]).stdout.strip();containers.append(observer)
 run(['cp',str(Path(__file__).with_name(name)),observer+':/tmp/'+name]);run(['start',observer])
 for _ in range(30):
  if run(['exec',observer,'test','-f','/tmp/trace-ready'],check=False).returncode==0:return observer
  state=json.loads(run(['inspect',observer]).stdout)[0]['State']
  if not state['Running']:raise AssertionError(run(['logs',observer]).stdout)
  time.sleep(.1)
 raise AssertionError('external syscall observer did not attach')


def finish_trace(run,observer):
 for _ in range(90):
  if not json.loads(run(['inspect',observer]).stdout)[0]['State']['Running']:break
  time.sleep(.1)
 else:raise AssertionError('external syscall observer not complete')
 text=run(['logs',observer]).stdout;result=json.loads(text);assert result['passed'],result
 assert not result.get('cleanup_error');return result


def correlate(trace,wire):
 assert not wire['trace_overflow'] and not wire['errors']
 calls=[r for r in wire['trace'] if r['direction']=='call']
 for sync in trace['syncs']:
  sync['rpc_calls']=[r for r in calls if sync['enter_ns']<=r['monotonic_ns']<=sync['exit_ns']]
 return trace
