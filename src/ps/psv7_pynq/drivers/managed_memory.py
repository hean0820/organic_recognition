"""Explicit, guarded BO release for the inspected PYNQ2.7 XRT backend."""
import ast
import inspect
import textwrap
from collections import Counter


def _body(function):
    node=ast.parse(textwrap.dedent(inspect.getsource(function))).body[0]
    return [part for part in node.body if not (isinstance(part,ast.Expr) and
            isinstance(part.value,ast.Constant) and isinstance(part.value.value,str))]


def _runtime_release_function():
    from pynq.buffer import PynqBuffer
    from pynq.pl_server.xrt_device import _xrt_allocate, _free_bo
    expected=ast.parse('''if hasattr(self, 'pointer') and self.pointer:
    if self.return_to:
        self.return_to.return_pointer(self.pointer)
    self.pointer = 0
''').body
    if ast.dump(ast.Module(body=_body(PynqBuffer.freebuffer),type_ignores=[])) != ast.dump(ast.Module(body=expected,type_ignores=[])):
        raise RuntimeError('Unsupported PYNQ release implementation; no buffers allocated')
    allocation=_body(_xrt_allocate)
    finalizer=ast.parse('''if pointer is not None:
    weakref.finalize(buf, _free_bo, device, bo, ar.virtual_address, ar.nbytes)
''').body[0]
    cache=ast.parse('''if cache is not None:
    ar.pointer = (bo, buf, device_address)
    ar.return_to = cache
''').body[0]
    if not any(ast.dump(part)==ast.dump(finalizer) for part in allocation) or not any(ast.dump(part)==ast.dump(cache) for part in allocation):
        raise RuntimeError('Unsupported PYNQ allocation implementation; no buffers allocated')
    calls=[node for part in allocation for node in ast.walk(part) if isinstance(node,ast.Call)
           and isinstance(node.func,ast.Attribute) and node.func.attr=='finalize']
    if len(calls)!=1:
        raise RuntimeError('Unexpected PYNQ finalizer; no buffers allocated')
    expected_release=ast.parse('''libc.munmap(ctypes.cast(ptr, ctypes.c_void_p), length)
xrt.xclFreeBO(device.handle, bo)
''').body
    if ast.dump(ast.Module(body=_body(_free_bo),type_ignores=[])) != ast.dump(ast.Module(body=expected_release,type_ignores=[])):
        raise RuntimeError('Unsupported XRT release primitive; no buffers allocated')
    return _free_bo


class _Allocation:
    def __init__(self, manager, role, guard):
        self.manager,self.role,self.guard=manager,role,guard
        self.frame=None;self.state='new'

    def attach(self, frame):
        # Retain the root strongly until explicit, guarded release. Ordinary
        # ndarray view destruction must never unmap an active DMA buffer.
        self.frame=frame
        self.bo=int(frame.bo);self.device=frame.device
        self.address=int(frame.virtual_address);self.nbytes=int(frame.nbytes)
        self.state='active'
        self.manager.active[id(self)]=self
        self.manager.allocated+=1
        pointer=getattr(frame,'pointer',None)
        if not isinstance(pointer,tuple) or len(pointer)!=3 or int(pointer[0])!=self.bo or getattr(frame,'return_to',None) is not self:
            raise RuntimeError('Allocator did not honor the inspected cache protocol; retain and stop')

    def return_pointer(self, pointer):
        if self.state=='released':return
        if self.state!='active':raise RuntimeError('BO release state uncertain; do not retry')
        if not self.guard():raise RuntimeError(self.role+' DMA is active; retain buffer')
        if self.frame is None or int(pointer[0])!=self.bo:
            raise RuntimeError('BO ownership mismatch; retain buffer')
        self.state='releasing'
        try:
            self.manager.release_function(self.device,self.bo,self.address,self.nbytes)
        except Exception:
            self.state='release_failed'
            raise
        self.frame.pointer=0
        self.frame=None
        self.state='released'
        self.manager.active.pop(id(self))
        self.manager.released+=1

    def release(self):
        if self.state=='released':return
        self.return_pointer((self.bo,None,None))


class ManagedAllocator:
    def __init__(self, device, allocate_function=None, release_function=None):
        if allocate_function is None:
            from pynq import allocate
            allocate_function=allocate
        self.device=device;self.allocate_function=allocate_function
        self.release_function=release_function or _runtime_release_function()
        self.active={};self.allocated=0;self.released=0

    def for_owner(self, role, guard):
        def allocate(shape,dtype):
            owner=_Allocation(self,role,guard)
            frame=self.allocate_function(shape=shape,dtype=dtype,target=self.device,cache=owner)
            owner.attach(frame)
            return frame
        return allocate

    def release_idle_remaining(self):
        # Handles an allocation failure before a frame was appended to its
        # role's list. Every individual owner still has to pass its halt guard.
        for owner in list(self.active.values()):owner.release()

    def status(self):
        return {'active_bos':len(self.active),'active_bytes':sum(o.nbytes for o in self.active.values()),
                'allocated_bos':self.allocated,'released_bos':self.released,
                'roles':dict(Counter(o.role for o in self.active.values()))}


def cma_snapshot():
    from pathlib import Path
    file=Path('/proc/meminfo')
    if not file.is_file():return None
    return {line.split(':',1)[0]:int(line.split()[1]) for line in file.read_text().splitlines()
            if line.startswith(('CmaTotal:','CmaFree:'))}


def driver_memory_snapshot(device):
    try:
        memory=device.default_memory
        return {'num_buffers':int(memory.num_buffers),'mem_used':int(memory.mem_used)}
    except Exception as error:
        return {'unavailable':repr(error)}
