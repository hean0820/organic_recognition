"""Read-only snapshots / guarded recovery for the unified CNN ABI."""
from pathlib import Path
from .unified_cnn import UnifiedCnn
class CnnControl:
    def __init__(self,cnn):self.owner=UnifiedCnn(cnn,None,Path(__file__).resolve().parents[1]/'assets/cnn_rtl_contract.json')
    def snapshot(self):return self.owner.snapshot()
    def recover(self):return self.owner.recover()
