# SPDX-License-Identifier: GPL-3.0-or-later
"""Process ownership and a lifetime project lock, independent of bpy."""
import os,threading,time

def watch_owner(pid):
    if pid is None:return
    if pid<=0 or os.getppid()!=pid:raise RuntimeError('The Blender worker owner changed before startup.')
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        api=ctypes.WinDLL('kernel32',use_last_error=True)
        api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];api.OpenProcess.restype=wintypes.HANDLE
        api.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];api.WaitForSingleObject.restype=wintypes.DWORD
        api.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=api.OpenProcess(0x100000,False,pid)
        if not handle:raise RuntimeError('Cannot monitor the Blender worker owner.')
        def watch():
            try:
                while api.WaitForSingleObject(handle,1000)==258:pass
                os._exit(0)
            finally:api.CloseHandle(handle)
    else:
        def watch():
            while os.getppid()==pid:time.sleep(.5)
            os._exit(0)
    threading.Thread(target=watch,name='Blender bridge owner',daemon=True).start()

def lock_project(root,timeout=5):
    stream=(root/'worker.lock').open('a+b');deadline=time.monotonic()+timeout
    while True:
        try:
            stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            return stream  # Keep open for the worker's entire life.
        except OSError as error:
            if time.monotonic()>=deadline:
                stream.close();raise RuntimeError('This Blender project is already open in another worker. Close its owning bridge or workspace before reopening it.') from error
            time.sleep(.1)
