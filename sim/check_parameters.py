"""Check final parameter identity across ROM COE, DDR blobs and model contract."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def coe(p):
    text=p.read_text(encoding='ascii')
    radix=int(re.search(r'memory_initialization_radix\s*=\s*(\d+)',text,re.I).group(1))
    body=re.search(r'memory_initialization_vector\s*=\s*([^;]+)',text,re.I|re.S).group(1)
    return np.array([int(v.strip(),radix) for v in body.split(',') if v.strip()],dtype=np.uint64)

def check(root=ROOT):
    root=Path(root)
    final=root/'data/model/final_parameters'
    manifest=json.loads((final/'manifest.json').read_text(encoding='utf-8'))
    ps=root/'src/ps/psv7_pynq'
    contract=json.loads((ps/'assets/cnn_rtl_contract.json').read_text(encoding='utf-8'))
    front=root/'src/rtl/cnn/frontend'
    checks=[]
    for name,ic in [('conv1',1),('conv2',24)]:
        w=np.fromfile(final/(name+'_weight_int8.bin'),np.uint8).reshape(-1,ic,3,3)
        for bank in range(3):
            if not np.array_equal(coe(front/(name+'_weight_r'+str(bank)+'.coe')),w[:,:,bank,:].ravel()):
                raise ValueError('ROM weights differ: '+name+' bank '+str(bank))
            checks.append(name+'_weight_bank_'+str(bank))
        b=np.fromfile(final/(name+'_bias_int32.bin'),'<u4')
        if not np.array_equal(coe(front/(name+'_bias_int32.coe')),b):raise ValueError('ROM bias differs')
        checks.append(name+'_bias')
    weights=b''.join((final/(n+'_weight_int8.bin')).read_bytes() for n in ['conv3','fc1','fc2'])
    biases=b''.join((final/(n+'_bias_int32.bin')).read_bytes() for n in ['conv3','fc1','fc2'])
    for name,data in [('cnn_model_weights.bin',weights),('cnn_model_bias.bin',biases)]:
        path=ps/'assets'/name
        if path.read_bytes()!=data or sha(path)!=contract['assets_sha256'][name]:
            raise ValueError('Runtime DDR parameters differ: '+name)
        checks.append(name)
    layout=json.loads((root/'build/layout_manifest.json').read_text(encoding='utf-8'))
    cnn_entries={row['destination']:row for row in layout['entries']
                 if row['destination'].startswith('vivado/ip_repo/cnn_rtl_unified/rtl/')}
    canonical=list((root/'src/rtl/cnn').rglob('*'))
    canonical=[p for p in canonical if p.is_file()]
    if len(cnn_entries)!=len(canonical):raise ValueError('CNN build source count differs')
    for p in canonical:
        relative=p.relative_to(root/'src/rtl/cnn').as_posix()
        row=cnn_entries.get('vivado/ip_repo/cnn_rtl_unified/rtl/'+relative)
        if row is None or row['source']!='src/rtl/cnn/'+relative or row['sha256']!=sha(p):
            raise ValueError('Canonical CNN source mapping differs: '+relative)
    multipliers=[manifest['layers'][n]['requant_multiplier_q30'] for n in ['conv1','conv2','conv3','fc1']]
    if multipliers!=[3561711,3526514,6503432,3488065]:raise ValueError('Frozen quantization differs')
    return {'passed':True,'checks':checks,'source_model_sha256':manifest['source_checkpoint_sha256'],
            'channels':manifest['channels'],'fc_shape':manifest['fc_shape'],
            'canonical_cnn_sources_mapped_to_build_ip':True,'hardware_accessed':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args()
    print(json.dumps(check(args.root),indent=2))
