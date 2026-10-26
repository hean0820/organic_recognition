"""Bulk CNN windows through the existing PYNQ2.7 MEMORY_MAPPED uint32 view.
No mapping, Overlay, DMA allocation or command-register ownership is created.
Source contract: Xilinx/PYNQ v2.7.0 pynq/mmio.py, MEMORY_MAPPED branch.
"""
import ctypes
import sys
import numpy as np

class NativeCnnTransfer:
    backend='NATIVE_C_VOLATILE_U32'
    def __init__(self,mmio,library):
        array=getattr(mmio,'array',None)
        device=getattr(mmio,'device',None)
        if (sys.byteorder!='little' or getattr(mmio,'base_addr',None)!=0x43C00000 or
                getattr(mmio,'length',None)!=0x10000 or device is None or
                not device.has_capability('MEMORY_MAPPED')):
            raise RuntimeError('CNN fast path requires the reviewed local MEMORY_MAPPED device and address')
        if (not isinstance(array,np.ndarray) or array.dtype!=np.uint32 or array.ndim!=1 or
                not array.flags.c_contiguous or not array.flags.writeable or array.nbytes<mmio.length or
                int(array.ctypes.data)&3):
            raise RuntimeError('CNN MMIO is not a contiguous writable aligned uint32 mapping')
        self.mmio=mmio;self.array=array;self.library=library
        self.address=int(array.ctypes.data);self.length=int(mmio.length)
        for name,args in (
          ('psv7_cnn_write_input',[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32]),
          ('psv7_cnn_verify_input',[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_void_p]),
          ('psv7_cnn_read_logits',[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32])):
            function=getattr(library,name);function.argtypes=args;function.restype=ctypes.c_int

    @staticmethod
    def validate_input(image):
        if not isinstance(image,np.ndarray) or image.dtype!=np.uint8 or image.shape!=(64,64) or not image.flags.c_contiguous:
            raise ValueError('CNN native input must be contiguous 64x64 uint8')

    def write_input(self,image):
        self.validate_input(image)
        if self.library.psv7_cnn_write_input(self.address,self.length,image.ctypes.data,image.nbytes):
            raise RuntimeError('CNN native input write contract failed')

    def verify_input(self,image):
        self.validate_input(image);mismatch=ctypes.c_uint32(0xffffffff)
        result=self.library.psv7_cnn_verify_input(self.address,self.length,image.ctypes.data,image.nbytes,ctypes.byref(mismatch))
        if result:raise RuntimeError('CNN input readback mismatch or invalid map at word '+str(mismatch.value))

    def read_logits(self):
        logits=np.empty(22,np.int32)
        if self.library.psv7_cnn_read_logits(self.address,self.length,logits.ctypes.data,22):
            raise RuntimeError('CNN native logits read contract failed')
        return logits

class PythonReferenceCnnTransfer:
    """Explicit benchmark of the accepted 0.6.1 per-word transfer loops.
    Never selected automatically as a fallback in the formal application.
    """
    backend='PYTHON_PER_WORD_0_6_1_REFERENCE'
    def __init__(self,mmio):self.mmio=mmio
    def write_input(self,image):
        NativeCnnTransfer.validate_input(image);raw=image.tobytes()
        for offset in range(0,4096,4):
            self.mmio.write(0x1000+offset,int.from_bytes(raw[offset:offset+4],'little'))
    def verify_input(self,image):
        NativeCnnTransfer.validate_input(image);raw=image.tobytes()
        for offset in range(0,4096,4):
            if int(self.mmio.read(0x1000+offset))!=int.from_bytes(raw[offset:offset+4],'little'):
                raise RuntimeError('CNN reference input readback mismatch')
    def read_logits(self):
        words=np.array([int(self.mmio.read(0x4000+4*i)) for i in range(22)],dtype=np.uint32)
        return words.view(np.int32)
