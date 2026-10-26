"""Recompute saved board measurements and exact logits checks; never access PL."""
import json
from collections import Counter
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'sim/ps_vs_rtl'))
from board_benchmark import summarize

def audit():
    with np.load(ROOT/'sim/ps_vs_rtl/assets/vectors.npz',allow_pickle=False) as data:
        expected=data['logits'].copy()
    results={}
    for name in ['current']:
        r=json.loads((ROOT/'board/results'/name/'board_result.json').read_text(encoding='utf-8'))
        if not r['passed'] or not r['hardware_accessed'] or len(r['records'])!=132:raise ValueError('Invalid saved board session')
        if Counter(x['order'] for x in r['records'])!={'CPU_THEN_RTL':66,'RTL_THEN_CPU':66}:raise ValueError('Unbalanced timing orders')
        for x in r['records']:
            if not x['exact_logits_match']:raise ValueError('Board reported a mismatch')
            # All retained board records contain the 22-element signed output.
            for key in ['ps_logits','rtl_logits','cpu_logits','logits']:
                if key in x and not np.array_equal(np.asarray(x[key],dtype=np.int32),expected[x['case_index']]):
                    raise ValueError('Saved logits differ from frozen vectors: '+key)
        calculated=summarize(r['records'])
        for group in ['ps_software','rtl_call']:
            if abs(calculated[group]['mean_ms']-r['summary'][group]['mean_ms'])>1e-9:raise ValueError('Timing summary differs')
        results[name]=calculated
    return {'passed':True,'saved_sessions':results,'current_ps_to_rtl_ratio':results['current']['ps_software']['mean_ms']/results['current']['rtl_call']['mean_ms'],
            'scope':'Audit of supplied current four-lane board measurements only; not a new board run','hardware_accessed':False}

if __name__=='__main__':print(json.dumps(audit(),indent=2))
