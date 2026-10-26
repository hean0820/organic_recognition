"""三层候选训练集标定、INT8导出与双参考逐值验证；不接触板卡。"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import shutil
import sys
import time
from datetime import datetime, timezone

import numpy as np
import torch
import torch.nn.functional as F

WORK = Path(__file__).resolve().parents[2]
TRAIN = WORK/'02_training'
SRC = TRAIN/'python_train/python_train'
sys.path.insert(0, str(SRC))
from organic_cnn3_model import OrganicCNN3
from export_pl_int8 import fuse_conv_bn, fuse_classifier, write_parameter_files, q30_multiplier
from integer_reference import IntegerReference, rounded_q30 as numpy_q30


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def fused_forward(x, params, activations=False):
    result = {}
    for i in range(1, 4):
        name = f'conv{i}'; weight, bias = params[name]
        x = F.relu(F.conv2d(x, weight, bias, padding=1))
        result[name+'_relu'] = x
        x = F.max_pool2d(x, 2)
    x = x.flatten(1)
    weight, bias = params['fc1']; x = F.relu(F.linear(x, weight, bias))
    result['fc1_relu'] = x
    weight, bias = params['fc2']; logits = F.linear(x, weight, bias)
    return (logits, result) if activations else logits


def torch_q30(acc, multiplier):
    product = acc.long()*int(multiplier)
    return torch.where(product >= 0, (product+(1 << 29)) >> 30,
                       -(((-product)+(1 << 29)) >> 30))


class TorchIntegerReference:
    """FP64卷积/线性求整数和，检查残差后取整；Q30全部INT64算术。"""
    def __init__(self, quantized, metadata, device):
        self.params = {k:(w.to(device).double(), b.to(device).double()) for k,(w,b) in quantized.items()}
        self.metadata = metadata
        self.device = device
        self.max_fractional_residual = 0.0

    def accumulator(self, value):
        rounded = value.round()
        residual = float((value-rounded).abs().max())
        self.max_fractional_residual = max(self.max_fractional_residual, residual)
        if residual >= 0.01:
            raise RuntimeError('FP64 integer-sum residual too large')
        acc = rounded.long()
        if int(acc.min()) < -(1 << 31) or int(acc.max()) >= (1 << 31):
            raise OverflowError('INT32 overflow')
        return acc

    @torch.inference_mode()
    def infer(self, images, keep_layers=False):
        if images.dtype != torch.uint8:
            raise TypeError('Integer reference input must be uint8')
        x = images.to(self.device).double()
        layers = {'input_uint8': images.cpu().numpy()} if keep_layers else {}
        for i in range(1, 4):
            name = f'conv{i}'; w,b = self.params[name]
            acc = self.accumulator(F.conv2d(x, w, b, padding=1))
            relu = torch_q30(acc, self.metadata[name]['requant_multiplier_q30']).clamp(0, 127)
            x = F.max_pool2d(relu.double(), 2)
            if keep_layers:
                layers[name+'_acc_int32'] = acc.cpu().numpy().astype(np.int32)
                layers[name+'_relu_int8'] = relu.cpu().numpy().astype(np.int8)
                layers[f'pool{i}_int8'] = x.cpu().numpy().astype(np.int8)
        x = x.flatten(1); w,b = self.params['fc1']
        acc = self.accumulator(F.linear(x, w, b))
        hidden = torch_q30(acc, self.metadata['fc1']['requant_multiplier_q30']).clamp(0, 127)
        w,b = self.params['fc2']; logits = self.accumulator(F.linear(hidden.double(), w,b))
        if keep_layers:
            layers['fc1_acc_int32'] = acc.cpu().numpy().astype(np.int32)
            layers['fc1_relu_int8'] = hidden.cpu().numpy().astype(np.int8)
            layers['fc2_logits_int32'] = logits.cpu().numpy().astype(np.int32)
        return logits.cpu().numpy().astype(np.int32), layers


def metrics(logits, y, names):
    predicted = logits.argmax(1)
    cm = np.zeros((22, 22), dtype=np.int64)
    np.add.at(cm, (y, predicted), 1)
    return {'correct': int((predicted == y).sum()), 'total': len(y),
        'accuracy': float((predicted == y).mean()),
        'per_class': [{'id': i, 'name': names[i], 'correct': int(cm[i,i]),
                       'total': int(cm[i].sum()), 'recall': float(cm[i,i]/cm[i].sum())} for i in range(22)],
        'ethanol_to_acid': int(cm[4,8]), 'acid_to_ethanol': int(cm[8,4])}, cm


def parameter_roundtrip(out, params, meta):
    checks = []
    rows_dir = out/'conv_weight_rows'; rows_dir.mkdir()
    row_index = {}
    for name,(w,b) in params.items():
        for kind, value, suffix in [('weight',w,'int8'), ('bias',b,'int32')]:
            arr = value.numpy().astype(np.int8 if suffix == 'int8' else '<i4')
            base = out/f'{name}_{kind}_{suffix}'
            write_parameter_files(base, arr)
            raw = np.fromfile(base.with_suffix('.bin'), dtype=arr.dtype).reshape(arr.shape)
            tokens = base.with_suffix('.hex').read_text(encoding='ascii').split()
            body = base.with_suffix('.coe').read_text(encoding='ascii').split('memory_initialization_vector=')[1].split(';')[0]
            coe_tokens = [s.strip() for s in body.split(',') if s.strip()]
            mask = 0xff if suffix == 'int8' else 0xffffffff
            expected = [int(v)&mask for v in arr.flat]
            assert np.array_equal(raw, arr)
            assert [int(t,16) for t in tokens] == expected == [int(t,16) for t in coe_tokens]
            checks.append({'tensor': name+'_'+kind, 'shape': list(arr.shape), 'formats': ['bin','hex','coe'], 'passed': True})
        if name.startswith('conv'):
            weights = w.numpy(); oc, ic = weights.shape[:2]
            chunks = []; decoded = []
            for i, ids in enumerate(np.array_split(np.arange(oc), 3)):
                part = weights[ids].reshape(-1,9)
                # 每个文本行是9个8位元素，不是一个72位ROM字。
                cells = [','.join(f'{int(v)&255:02X}' for v in row) for row in part]
                path = rows_dir/f'{name}_weight_rows_{i}.coe'
                path.write_text('memory_initialization_radix=16;\nmemory_initialization_vector=\n'+',\n'.join(cells)+';\n',encoding='ascii')
                body = path.read_text(encoding='ascii').split('memory_initialization_vector=')[1].split(';')[0]
                unsigned = np.array([int(v.strip(),16) for v in body.replace('\n',',').split(',') if v.strip()],dtype=np.uint8)
                decoded.append(unsigned.view(np.int8))
                chunks.append({'file': path.name, 'oc_start':int(ids[0]), 'oc_stop_exclusive':int(ids[-1]+1),
                               'row_start':int(ids[0])*ic, 'row_stop_exclusive':int(ids[-1]+1)*ic})
            assert np.array_equal(np.concatenate(decoded), weights.reshape(-1))
            row_index[name] = {'shape':list(weights.shape), 'element_bits':8, 'elements_per_text_row':9,
                               'row_address':'oc * IC + ic', 'chunks':chunks, 'roundtrip_passed':True}
    save(rows_dir/'index.json', row_index)
    return checks


def numeric_cases():
    zero = np.zeros((64,64),np.uint8)
    top = zero.copy(); top[0,0]=255
    bottom = zero.copy(); bottom[-1,-1]=255
    border = zero.copy(); border[[0,-1],:]=255; border[:,[0,-1]]=255
    line = zero.copy(); line[:,32]=255
    return {'zero':zero, 'full255':np.full_like(zero,255), 'full127':np.full_like(zero,127),
            'checkerboard':((np.indices((64,64)).sum(0)%2)*255).astype(np.uint8),
            'top_left_impulse':top, 'bottom_right_impulse':bottom, 'border255':border,
            'center_line':line, 'full1':np.ones_like(zero),
            'horizontal_ramp':np.tile(np.linspace(0,255,64).round().astype(np.uint8),(64,1))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--activation-calibration', choices=['max','mse'], default='max')
    parser.add_argument('--calibration', type=Path, default=TRAIN/'organic_data/original_photos_dataset/train_original_photos.npz')
    args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(4)
    torch.backends.cudnn.allow_tf32 = False; torch.backends.cuda.matmul.allow_tf32 = False
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    started = time.perf_counter()
    source_cp = args.checkpoint.resolve()
    cp = torch.load(source_cp, map_location='cpu', weights_only=False)
    names = cp['class_names']
    assert names == json.loads((TRAIN/'organic_data/class_names.json').read_text(encoding='utf-8'))
    fixed = cp.get('fixed_quantization')
    if fixed is not None:
        channels = tuple(cp['channels'])
        float_params = cp['fused_params']
        if set(float_params) != {'conv1','conv2','conv3','fc1','fc2'}:
            raise ValueError('Invalid fused QAT checkpoint')
    else:
        channels = tuple(int(cp['model_state'][f'features.{4*i}.weight'].shape[0]) for i in range(3))
        model = OrganicCNN3(len(names),channels).eval().to(device)
        model.load_state_dict(cp['model_state'],strict=True)
        float_params = {f'conv{i+1}':fuse_conv_bn(model.features[4*i], model.features[4*i+1]) for i in range(3)}
        float_params['fc1'] = (model.embedding[1].weight.detach().cpu(),model.embedding[1].bias.detach().cpu())
        float_params['fc2'] = fuse_classifier(model)
    gpu_params = {k:(w.to(device),b.to(device)) for k,(w,b) in float_params.items()}
    val_path = TRAIN/'organic_data/original_photos_dataset/val_original_photos.npz'
    if args.calibration.resolve() == val_path.resolve():
        raise ValueError('Validation cannot be used for calibration')
    with np.load(val_path,allow_pickle=False) as data:
        vx = torch.from_numpy(data['x']).float(); vy = data['y']
    with np.load(args.calibration,allow_pickle=False) as data:
        calibration_x = torch.from_numpy(data['x']).float()
    assert tuple(vx.shape) == (910,1,64,64) and tuple(calibration_x.shape) == (3175,1,64,64)
    fp_logits = []; fused_logits = []; fusion_max_error = 0.
    with torch.inference_mode():
        for start in range(0,len(vx),32):
            x = vx[start:start+32].to(device)
            fused = fused_forward(x,gpu_params)
            original = fused if fixed is not None else model(x)
            fusion_max_error = max(fusion_max_error, float((original-fused).abs().max()))
            fp_logits.append(original.cpu().numpy()); fused_logits.append(fused.cpu().numpy())
    fp_logits = np.concatenate(fp_logits); fused_logits=np.concatenate(fused_logits)
    assert fusion_max_error < 1e-4 and np.array_equal(fp_logits.argmax(1),fused_logits.argmax(1))
    fp_metrics,_ = metrics(fp_logits,vy,names)
    assert abs(fp_metrics['accuracy']-float(cp['val_acc'])) < 1e-10
    print(f'FP32/fusion verified: {fp_metrics["correct"]}/910, fusion_max={fusion_max_error:.8g}',flush=True)
    maxima = {name+'_relu':0.0 for name in ('conv1','conv2','conv3','fc1')}
    calibration_samples={name:[] for name in maxima}
    with torch.inference_mode():
        for start in range(0,len(calibration_x),32):
            _,activations = fused_forward(calibration_x[start:start+32].to(device),gpu_params,True)
            for name,tensor in activations.items():
                maxima[name]=max(maxima[name],float(tensor.max()))
                if args.activation_calibration=='mse':
                    flat=tensor.flatten()
                    indices=torch.linspace(0,len(flat)-1,min(8192,len(flat)),device=device).long()
                    calibration_samples[name].append(flat[indices].cpu().numpy())
    scales = {k:(v/127 if v else 1.) for k,v in maxima.items()}
    if fixed is not None:
        scales = {name+'_relu':fixed[name]['output_scale'] for name in ('conv1','conv2','conv3','fc1')}
        if args.activation_calibration != 'max':
            raise ValueError('Fixed-QAT scales must not be recalibrated with MSE')
    mse_details={}
    if args.activation_calibration=='mse':
        for name,parts in calibration_samples.items():
            values=np.concatenate(parts).astype(np.float64)
            candidates=sorted(set([float(np.quantile(values,q)) for q in
                                   (0.99,0.995,0.999,0.9995,0.9999,0.99995)]+[maxima[name]]))
            candidates=[v for v in candidates if v>0]
            table=[]
            for maximum in candidates:
                scale=maximum/127
                reconstructed=np.floor(values/scale+0.5).clip(0,127)*scale
                table.append({'range_max':maximum,'mse':float(np.mean((values-reconstructed)**2)),
                              'sample_clipping_fraction':float(np.mean(values>maximum))})
            chosen=min(table,key=lambda row:row['mse'])
            scales[name]=chosen['range_max']/127
            mse_details[name]={'sample_count':len(values),'selection_uses_validation':False,
                               'candidates':table,'chosen':chosen}
    metadata={}; quantized={}; bounds={}
    input_scale=1/255
    for name,(w,b) in float_params.items():
        weight_scale=fixed[name]['weight_scale'] if fixed is not None else (float(w.abs().max())/127 or 1.)
        qweight=torch.round(w.double()/weight_scale).clamp(-127,127).to(torch.int8)
        bias_scale=input_scale*weight_scale
        qb=torch.round(b.double()/bias_scale)
        assert float(qb.min()) >= -(1 << 31) and float(qb.max()) < (1 << 31)
        qbias=qb.to(torch.int32); quantized[name]=(qweight,qbias)
        meta={'input_scale':input_scale,'weight_scale':weight_scale,'bias_scale':bias_scale,
              'weight_shape':list(w.shape),'bias_shape':list(b.shape)}
        max_input=255 if name=='conv1' else 127
        abs_bound=qweight.long().abs().reshape(qweight.shape[0],-1).sum(1)*max_input+qbias.long().abs()
        assert int(abs_bound.max()) < (1 << 31)
        bound={'max_absolute_accumulator_bound':int(abs_bound.max()),'int32_safe':True,
               'input_max':max_input,'method':'input_max * sum(abs(weight)) + abs(bias), per output channel'}
        if name!='fc2':
            output_scale=scales[name+'_relu']
            multiplier=q30_multiplier(bias_scale/output_scale)
            if fixed is not None:
                assert multiplier == fixed[name]['requant_multiplier_q30']
            meta.update(output_scale=output_scale,requant_multiplier_q30=multiplier,
                        requant_real_multiplier=bias_scale/output_scale,requant_right_shift=30,
                        output_min=0,output_max=127)
            bound['max_absolute_q30_product_bound']=int(abs_bound.max())*multiplier
            assert bound['max_absolute_q30_product_bound']+(1 << 29)<(1 << 63)
            input_scale=output_scale
        else: meta['logit_scale']=bias_scale
        metadata[name]=meta; bounds[name]=bound
    format_checks=parameter_roundtrip(out,quantized,metadata)
    manifest={'format_version':2,'status':'offline_candidate_in_progress','model_id':sha(source_cp)[:16],
        'source_checkpoint':str(source_cp),'source_checkpoint_sha256':sha(source_cp),
        'source_validation_accuracy':fp_metrics['accuracy'],'num_conv_layers':3,
        'channels':[1]+list(channels),'fc_shape':[3072,48,22],'classes':22,'class_names':names,
        'input':{'shape':[1,64,64],'dtype':'uint8','scale':1/255,'order':'CHW_X_FASTEST','zero_point':0},
        'weights':{'dtype':'int8','range':[-127,127],'zero_point':0,'rounding':'nearest_ties_to_even'},
        'bias':{'dtype':'int32','endianness':'little','rounding':'nearest_ties_to_even'},
        'accumulator':{'dtype':'int32','overflow':'forbidden; proven bounds in numeric_bounds.json'},
        'activation':{'dtype':'int8','range_after_relu':[0,127],'zero_point':0},
        'requantization':{'formula':'round_away_from_zero(acc * multiplier_q30 / 2^30)',
                          'right_shift':30,'intermediate_product':'signed int64','relu_then_range':[0,127]},
        'conv':{'kernel':[3,3],'stride':1,'padding':1,'weight_order':'OC_IC_KY_KX'},
        'pool':{'kernel':[2,2],'stride':2,'type':'max','after_each_conv':True},
        'fc_weight_order':'OUT_IN','fc2_output':'22 raw signed INT32 logits; no ReLU or requant',
        'layers':metadata,'calibration':{'source':str(args.calibration.resolve()),'sha256':sha(args.calibration),
            'images':len(calibration_x),'method':('QAT keeps baseline training-only scales and Q30; maxima recorded only'
                if fixed is not None else 'training-only maximum after fused ReLU / 127'
                if args.activation_calibration=='max' else 'training-only sampled positive-round quantization MSE minimization'),
            'activation_maxima':maxima,'activation_scales':scales,
            'mse_details':mse_details,'validation_used':False},
        'validation_file_sha256':sha(val_path),'fusion_max_abs_error':fusion_max_error,
        'hardware_protocol_id':None,'old_overlay_compatible':False,'hardware_accessed':False,
        'independent_field_tested':False,'fp32_metrics':fp_metrics}
    if fixed is not None:
        manifest['qat'] = {'epoch':cp['epoch'],'training_config':cp['training_config'],
                           'fake_quant_validation_correct':cp['qat_validation_correct'],
                           'all_scales_fixed':True,'bn_and_auxiliary_heads_already_fused':True}
    save(out/'manifest.json',manifest); save(out/'class_names.json',names)
    save(out/'numeric_bounds.json',bounds); save(out/'parameter_roundtrip.json',format_checks)
    np.savez_compressed(out/'fc_parameters_cnn3_candidate.npz',
        w1=quantized['fc1'][0].numpy(),b1=quantized['fc1'][1].numpy(),
        w2=quantized['fc2'][0].numpy(),b2=quantized['fc2'][1].numpy(),
        multiplier_q30=np.array(metadata['fc1']['requant_multiplier_q30'],dtype=np.int64))
    torch_ref=TorchIntegerReference(quantized,metadata,device)
    images=(vx*255).round().clamp(0,255).to(torch.uint8)
    int_logits=[]
    for start in range(0,len(images),16):
        logits,_=torch_ref.infer(images[start:start+16]); int_logits.append(logits)
    int_logits=np.concatenate(int_logits)
    int_metrics,cm=metrics(int_logits,vy,names)
    print(f'INT8 candidate: {int_metrics["correct"]}/910 ({int_metrics["accuracy"]:.4%}); starting independent NumPy checks',flush=True)
    reference=IntegerReference(out)
    mismatches=[]; np_logits=[]
    for i,image in enumerate(images.numpy()):
        result=reference.infer(image); logits=result['fc2_logits_int32'][0]; np_logits.append(logits)
        if not np.array_equal(logits,int_logits[i]): mismatches.append(i)
        if (i+1)%100==0: print(f'Independent integer comparison: {i+1}/910; mismatches={len(mismatches)}',flush=True)
    if mismatches: raise RuntimeError(f'Integer references differ: {mismatches[:10]}')
    np.savez_compressed(out/'validation_predictions.npz',labels=vy,fp32_logits=fp_logits,
                        int8_logits=int_logits,int8_predicted=int_logits.argmax(1))
    np.savetxt(out/'confusion_matrix_int8.csv',cm,fmt='%d',delimiter=',')
    with (out/'validation_predictions.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream); writer.writerow(['validation_index','true_id','fp32_id','int8_id','int8_correct'])
        writer.writerows((i,int(y),int(f),int(q),int(y==q)) for i,(y,f,q) in enumerate(zip(vy,fp_logits.argmax(1),int_logits.argmax(1))))
    golden_dir=out/'golden'; golden_dir.mkdir()
    samples=[]
    for c in range(22):
        indices=np.flatnonzero(vy==c)
        for index in (int(indices[0]),int(indices[len(indices)//2])):
            samples.append((f'class{c:02d}_val{index:04d}',images[index].numpy(),c,'validation',index))
    for name,image in numeric_cases().items(): samples.append(('numeric_'+name,image,None,'synthetic',None))
    captures=sorted((WORK.parent/'reports/camera_accuracy/2026-10-15/captures').glob('*/input64.npy'))
    for path in captures: samples.append(('known_'+path.parent.name,np.load(path,allow_pickle=False),4,'known_ethanol_diagnostic',None))
    golden_records=[]; diagnostic=[]
    for stem,image,expected,kind,index in samples:
        image=np.asarray(image,dtype=np.uint8).reshape(1,64,64)
        layers=reference.infer(image)
        _,second=torch_ref.infer(torch.from_numpy(image[None]),True)
        if set(layers)!=set(second) or any(not np.array_equal(layers[k],second[k]) for k in layers):
            raise RuntimeError('Golden layer mismatch: '+stem)
        np.savez_compressed(golden_dir/(stem+'_layers.npz'),**layers)
        image.reshape(-1).tofile(golden_dir/(stem+'_input_uint8.bin'))
        layers['pool3_int8'].reshape(-1).tofile(golden_dir/(stem+'_features_uint8.bin'))
        layers['fc2_logits_int32'].astype('<i4').reshape(-1).tofile(golden_dir/(stem+'_logits_int32.bin'))
        prediction=int(layers['fc2_logits_int32'].argmax())
        record={'sample':stem,'kind':kind,'validation_index':index,'true_class':expected,
                'predicted_class':prediction,'all_13_layers_match':True,'layer_file':stem+'_layers.npz'}
        golden_records.append(record)
        if kind=='known_ethanol_diagnostic':diagnostic.append(record)
    # 有符号Q30边界用Python任意精度整数作第三种参考。
    q30_cases=[]
    for m in [0,1,1 << 29,(1 << 31)-1]+[metadata[n]['requant_multiplier_q30'] for n in ('conv1','conv2','conv3','fc1')]:
        acc=np.array([-(1 << 31),-1073741825,-3,-2,-1,0,1,2,3,1073741823,(1 << 31)-1],dtype=np.int64)
        expected=np.array([((-1 if int(v)*m<0 else 1)*((abs(int(v)*m)+(1 << 29))//(1 << 30))) for v in acc],dtype=np.int64)
        assert np.array_equal(numpy_q30(acc,m),expected)
        assert np.array_equal(torch_q30(torch.from_numpy(acc),m).numpy(),expected)
        q30_cases.append({'multiplier':m,'cases':len(acc),'passed':True})
    validation={'torch_numpy_logits_equal_all_910':True,'numpy_compared_samples':910,
        'golden_count':len(golden_records),'golden_layer_arrays_compared':13*len(golden_records),
        'golden_categories':{'validation':44,'synthetic':10,'known_diagnostic':len(captures)},
        'q30_boundary_tests':q30_cases,'parameter_roundtrip_passed':True,
        'fp64_integer_sum_max_fractional_residual':torch_ref.max_fractional_residual,
        'hardware_tested':False,'independent_field_tested':False}
    save(golden_dir/'index.json',golden_records); save(out/'software_validation.json',validation)
    save(out/'known_diagnostic.json',{'correct':sum(r['predicted_class']==4 for r in diagnostic),
         'total':len(diagnostic),'independent_test':False,'captures':diagnostic})
    source=out/'source_snapshot'; source.mkdir()
    for path in [Path(__file__),Path(__file__).parent/'integer_reference.py',SRC/'organic_torch_model.py',
                 SRC/'organic_cnn3_model.py',SRC/'export_pl_int8.py']:
        shutil.copy2(path,source/path.name)
    manifest.update(status='offline_integer_candidate_validated_pending_field_and_PL',
        int8_metrics=int_metrics,int8_reference_accuracy=int_metrics['accuracy'],
        accuracy_change_pp=100*(int_metrics['accuracy']-fp_metrics['accuracy']),
        golden_samples=golden_records,software_validation=validation,
        fc_interface={'input_bytes':3072,'input_words_u32':768,'weight_bytes':148512,
                      'weight_words_u32':37128,'bias_int32_values':70,'driver_adapted':False},
        completed_utc=datetime.now(timezone.utc).isoformat(),elapsed_seconds=time.perf_counter()-started)
    save(out/'manifest.json',manifest)
    save(out/'file_hashes.json',{'algorithm':'sha256','files':[
        {'path':p.relative_to(out).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)}
        for p in sorted(out.rglob('*')) if p.is_file() and p.name!='file_hashes.json']})
    print(json.dumps({'status':manifest['status'],'output':str(out),'fp32':fp_metrics['correct'],
        'int8':int_metrics['correct'],'accuracy_change_pp':manifest['accuracy_change_pp'],
        'golden':len(golden_records),'seconds':manifest['elapsed_seconds']},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__': main()
