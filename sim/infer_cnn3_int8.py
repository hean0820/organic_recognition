"""对一份已预处理input64执行软件整数推理，不导入PYNQ或接触板卡。"""
from pathlib import Path
import argparse
import hashlib
import json
import numpy as np
from integer_reference import IntegerReference


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--input64',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.output and args.output.exists(): raise FileExistsError(args.output)
    image=np.load(args.input64,allow_pickle=False)
    reference=IntegerReference(args.package)
    layers=reference.infer(image)
    logits=layers['fc2_logits_int32'].reshape(-1)
    predicted=int(logits.argmax())
    result={'package':str(args.package.resolve()),'source_checkpoint_sha256':reference.manifest['source_checkpoint_sha256'],
            'manifest_sha256':hashlib.sha256((args.package/'manifest.json').read_bytes()).hexdigest(),
            'input':str(args.input64.resolve()),'input_sha256':hashlib.sha256(args.input64.read_bytes()).hexdigest(),
            'input_normalization':'uint8 integer, no division before integer convolution',
            'predicted_class':predicted,'predicted_name':reference.manifest['class_names'][predicted],
            'logits_int32':logits.tolist(),'accuracy':None,'hardware_accessed':False}
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(text,encoding='utf-8')
    print(text)


if __name__=='__main__': main()
