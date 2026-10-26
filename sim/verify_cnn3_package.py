"""离线校验三层候选包的文件身份、FC资产、溢出界和59组Golden。"""
from pathlib import Path
import argparse
import hashlib
import json
import numpy as np
from integer_reference import IntegerReference


def verify(package):
    root=Path(package).resolve()
    hashes=json.loads((root/'file_hashes.json').read_text(encoding='utf-8'))
    for row in hashes['files']:
        path=(root/row['path']).resolve()
        try: path.relative_to(root)
        except ValueError: raise ValueError('Hash manifest contains path outside package')
        if not path.is_file() or path.stat().st_size!=row['bytes']:
            raise ValueError('Missing/size mismatch: '+row['path'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('SHA256 mismatch: '+row['path'])
    reference=IntegerReference(root); manifest=reference.manifest
    assert manifest['num_conv_layers']==3 and manifest['fc_shape']==[3072,48,22]
    assert manifest['class_names']==json.loads((root/'class_names.json').read_text(encoding='utf-8'))
    assert len(manifest['class_names'])==22 and len(set(manifest['class_names']))==22
    with np.load(root/'fc_parameters_cnn3_candidate.npz',allow_pickle=False) as fc:
        for key,name in [('w1','fc1_weight'),('b1','fc1_bias'),('w2','fc2_weight'),('b2','fc2_bias')]:
            assert np.array_equal(fc[key],reference.params[name])
        assert int(fc['multiplier_q30'])==manifest['layers']['fc1']['requant_multiplier_q30']
    weights_bytes=sum(reference.params[n].size for n in ('fc1_weight','fc2_weight'))
    assert weights_bytes==148512 and weights_bytes//4==37128
    assert 3072//4==manifest['fc_interface']['input_words_u32']==768
    bounds=json.loads((root/'numeric_bounds.json').read_text(encoding='utf-8'))
    for name in manifest['layers']:
        weights=reference.params[name+'_weight']; bias=reference.params[name+'_bias']
        maximum=255 if name=='conv1' else 127
        acc_bound=int((np.abs(weights).reshape(len(bias),-1).sum(1)*maximum+np.abs(bias)).max())
        assert acc_bound==bounds[name]['max_absolute_accumulator_bound']<(1 << 31)
        if name!='fc2':
            multiplier=manifest['layers'][name]['requant_multiplier_q30']
            assert 0<=multiplier<(1 << 31)
            assert acc_bound*multiplier+(1 << 29)<(1 << 63)
    index=json.loads((root/'golden/index.json').read_text(encoding='utf-8'))
    counts={}; class_counts=np.zeros(22,np.int64); compared=0
    for row in index:
        counts[row['kind']]=counts.get(row['kind'],0)+1
        if row['kind']=='validation': class_counts[row['true_class']]+=1
        stem=row['sample']; base=root/'golden'
        image=np.fromfile(base/(stem+'_input_uint8.bin'),np.uint8)
        assert image.size==4096
        actual=reference.infer(image.reshape(64,64))
        with np.load(base/row['layer_file'],allow_pickle=False) as saved:
            assert set(saved.files)==set(actual) and len(actual)==13
            for name,array in actual.items():
                assert saved[name].dtype==array.dtype and np.array_equal(saved[name],array), (stem,name)
                compared+=1
        feature=np.fromfile(base/(stem+'_features_uint8.bin'),np.uint8)
        logits=np.fromfile(base/(stem+'_logits_int32.bin'),'<i4')
        assert feature.size==3072 and np.array_equal(feature,actual['pool3_int8'].reshape(-1))
        assert logits.size==22 and np.array_equal(logits,actual['fc2_logits_int32'].reshape(-1))
        assert int(logits.argmax())==row['predicted_class']
    assert np.all(class_counts==2) and counts['synthetic']==10
    return {'passed':True,'package':str(root),'hashed_files':len(hashes['files']),
        'golden_samples_recomputed':len(index),'golden_layer_arrays_compared':compared,
        'golden_kinds':counts,'validation_class_coverage':22,'fc_asset_matches_bins':True,
        'int32_acc_and_int64_product_bounds_safe':True,
        'full_910_validation_recomputed_in_this_verifier':False,
        'hardware_accessed':False,'independent_field_tested':False,
        'accuracy_is_recorded_software_validation':manifest['int8_metrics']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    report=verify(args.package)
    text=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if args.report:
        target=args.report.resolve(); root=args.package.resolve()
        try: target.relative_to(root)
        except ValueError: pass
        else: raise ValueError('Write the verification report outside the frozen package')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(text,encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='accuracy_is_recorded_software_validation'},
                     ensure_ascii=False,indent=2))


if __name__=='__main__': main()
