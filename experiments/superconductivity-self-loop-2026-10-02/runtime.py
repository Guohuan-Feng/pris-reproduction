"""Durable local state, exclusive controller ownership, and cancellable children."""
from __future__ import annotations
from contextlib import contextmanager
import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
import uuid

def utc():return dt.datetime.now(dt.timezone.utc).isoformat()
def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with tmp.open('w',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    for n in range(6):
        try:os.replace(tmp,path);return
        except PermissionError:
            if n==5:raise
            time.sleep(.05*(n+1))

@contextmanager
def exclusive(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    f=path.open('a+b')
    if f.tell()==0:f.write(b'0');f.flush()
    f.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except (OSError,BlockingIOError):
        f.close();raise RuntimeError('This run already has an active owner')
    try:yield
    finally:
        f.seek(0)
        if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
        else:fcntl.flock(f.fileno(),fcntl.LOCK_UN)
        f.close()

class Store:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.root/'memory.sqlite',timeout=20)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL); CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL);')
    def state(self):
        row=self.db.execute('SELECT payload FROM state WHERE id=1').fetchone()
        return json.loads(row[0]) if row else None
    def save(self,state,kind,payload=None):
        with self.db:
            self.db.execute('INSERT INTO state(id,payload) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(json.dumps(state,ensure_ascii=False,allow_nan=False),))
            self.db.execute('INSERT INTO events(at,kind,payload) VALUES(?,?,?)',(utc(),kind,json.dumps(payload or {},ensure_ascii=False,allow_nan=False)))
    def history(self):
        return [{'seq':r[0],'at':r[1],'kind':r[2],'payload':json.loads(r[3])} for r in self.db.execute('SELECT seq,at,kind,payload FROM events ORDER BY seq')]
    def export(self):
        write_json(self.root/'status.json',self.state())
        write_json(self.root/'memory_export.json',self.history())
    def close(self):self.db.close()

class Cancelled(RuntimeError):pass
class BudgetExpired(RuntimeError):pass

def kill_owned(proc):
    if proc.poll() is not None:return
    if os.name=='nt':subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True)
    else:
        import signal
        os.killpg(proc.pid,signal.SIGTERM)
    try:proc.wait(timeout=5)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()

def run_child(command,root,folder,timeout,stdin=None,env=None,tick=None):
    """All children share a run lock so orphaned work cannot overlap a resume."""
    root,folder=Path(root),Path(folder);folder.mkdir(parents=True,exist_ok=True)
    if (root/'STOP').exists():raise Cancelled('User cancellation requested')
    wrapper=Path(__file__).with_name('child_runner.py')
    import sys
    child_command=[sys.executable,'-X','utf8',str(wrapper),str(root/'child.lock'),'--',*command]
    t=time.monotonic()
    last=t
    with (folder/'stdout.jsonl').open('wb') as out,(folder/'stderr.log').open('wb') as err:
        proc=subprocess.Popen(child_command,stdin=subprocess.PIPE,stdout=out,stderr=err,env=env,start_new_session=os.name!='nt')
        write_json(folder/'process.json',{'pid':proc.pid,'started_utc':utc(),'command':command})
        try:
            if stdin is not None:proc.stdin.write(stdin.encode('utf-8'))
            proc.stdin.close()
            while proc.poll() is None:
                time.sleep(.2);now=time.monotonic()
                if tick and now-last>=1:
                    delta=now-last;last=now;tick(delta)
                if (root/'STOP').exists():raise Cancelled('User cancellation requested')
                if now-t>timeout:raise BudgetExpired('Child wall-time budget exhausted')
            if tick:
                now=time.monotonic();delta=now-last;last=now;tick(delta)
        except BaseException:
            kill_owned(proc)
            if tick:
                try:tick(time.monotonic()-last)
                except Exception:pass  # Preserve the cancellation/timeout that caused cleanup.
            raise
    return proc.returncode
