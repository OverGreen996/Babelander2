"""Read-only Windows process/whole-system samples for replay diagnostics."""
import ctypes
import json
from ctypes import wintypes
import subprocess
import threading
import time


class Memory(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in
      ('peak_working','working','peak_pool','pool','peak_nonpaged','nonpaged','pagefile','peak_pagefile','private')]


K=ctypes.windll.kernel32;PS=ctypes.windll.psapi
K.GetCurrentProcess.restype=wintypes.HANDLE
K.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];K.OpenProcess.restype=wintypes.HANDLE
K.CloseHandle.argtypes=[wintypes.HANDLE]
K.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
PS.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD]
K.GetSystemTimes.argtypes=[ctypes.POINTER(wintypes.FILETIME)]*3


def process(pid=None):
    handle=K.OpenProcess(0x410,False,pid) if pid else K.GetCurrentProcess()
    if not handle:return None
    try:
        m=Memory();m.cb=ctypes.sizeof(m);ts=[wintypes.FILETIME() for _ in range(4)]
        if not PS.GetProcessMemoryInfo(handle,ctypes.byref(m),m.cb):return None
        if not K.GetProcessTimes(handle,*[ctypes.byref(t) for t in ts]):return None
        return {'working_mib':round(m.working/1048576,2),'private_mib':round(m.private/1048576,2),
                'cpu_seconds':sum((t.dwHighDateTime<<32)+t.dwLowDateTime for t in ts[2:])/1e7}
    finally:
        if pid:K.CloseHandle(handle)


def system_stamps():
    ts=[wintypes.FILETIME() for _ in range(3)]
    if not K.GetSystemTimes(*[ctypes.byref(t) for t in ts]):return None
    return [(t.dwHighDateTime<<32)+t.dwLowDateTime for t in ts]


class Sampler:
    def __init__(self,report,state,pid):
        self.report,self.state,self.pid=report,state,pid
        self.stop_event=threading.Event()
        self.thread=threading.Thread(target=self.run,name='replay-resource-samples',daemon=True)
    def start(self):self.thread.start()
    def close(self):self.stop_event.set();self.thread.join(12)
    def run(self):
        before=system_stamps();last=time.perf_counter();next_owned_gpu=0.
        while not self.stop_event.wait(15):
            now=time.perf_counter();after=system_stamps()
            row={'at_perf_counter':now,'phase':(self.state.get('phase') or {}).get('label'),
                 'cpu_interval_seconds':now-last,'app':process(),'model':process(self.pid()) if self.pid() else None}
            if before and after:
                delta=[a-b for a,b in zip(after,before)];total=delta[1]+delta[2]
                row['whole_system_cpu_percent']=round(100*(total-delta[0])/total,2) if total else None
            before,last=after,now
            try:
                query=subprocess.run(['nvidia-smi','--query-gpu=utilization.gpu,memory.used,clocks.sm','--format=csv,noheader,nounits'],
                                     capture_output=True,text=True,timeout=5,creationflags=subprocess.CREATE_NO_WINDOW)
                values=query.stdout.strip().splitlines()[0].split(',')
                row.update(gpu_instant_percent=float(values[0]),gpu_whole_memory_mib=float(values[1]),gpu_clock_mhz=float(values[2]))
            except Exception as error:row['gpu_sample_error']=type(error).__name__
            owned_pid=self.pid()
            if owned_pid and now>=next_owned_gpu:
                next_owned_gpu=now+60
                command="Get-CimInstance -ClassName Win32_PerfFormattedData_GPUPerformanceCounters_GPUProcessMemory | Where-Object { $_.Name -like 'pid_"+str(int(owned_pid))+"_*' } | Select-Object Name,DedicatedUsage,SharedUsage | ConvertTo-Json -Compress"
                try:
                    query=subprocess.run(['powershell','-NoProfile','-Command',command],capture_output=True,text=True,timeout=5,creationflags=subprocess.CREATE_NO_WINDOW)
                    if query.returncode==0 and query.stdout.strip():
                        counters=json.loads(query.stdout);counters=counters if isinstance(counters,list) else [counters]
                        row['owned_gpu_process_memory']={'pid':owned_pid,'counter':'WDDM GPUProcessMemory',
                            'dedicated_mib':round(sum(int(r['DedicatedUsage']) for r in counters)/1048576,2),
                            'shared_mib':round(sum(int(r['SharedUsage']) for r in counters)/1048576,2)}
                    else:row['owned_gpu_process_memory']=None
                except Exception as error:row['owned_gpu_memory_error']=type(error).__name__
            self.report['system_load'].append(row)
