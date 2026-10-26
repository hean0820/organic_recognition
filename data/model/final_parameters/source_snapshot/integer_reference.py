"""独立NumPy INT64乘加参考；按清单读取候选包，不依赖PyTorch/PYNQ。"""
from pathlib import Path
import json
import numpy as np


def rounded_q30(acc, multiplier):
    if not 0 <= int(multiplier) <= np.iinfo(np.int32).max:
        raise ValueError('Multiplier must be nonnegative signed INT32')
    values = np.asarray(acc, dtype=np.int64)
    if np.any(values < np.iinfo(np.int32).min) or np.any(values > np.iinfo(np.int32).max):
        raise OverflowError('Accumulator outside signed INT32 contract')
    product = values * int(multiplier)
    return np.where(product >= 0, (product + (1 << 29)) >> 30,
                    -(((-product) + (1 << 29)) >> 30))


class IntegerReference:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.manifest = json.loads((self.folder/'manifest.json').read_text(encoding='utf-8'))
        self.params = {}
        for layer, meta in self.manifest['layers'].items():
            for kind, dtype, suffix in [('weight', np.int8, 'int8'), ('bias', '<i4', 'int32')]:
                data = np.fromfile(self.folder/f'{layer}_{kind}_{suffix}.bin', dtype=dtype)
                self.params[layer+'_'+kind] = data.reshape(meta[kind+'_shape']).astype(np.int64)

    @staticmethod
    def checked_int32(array):
        if np.any(array < -(1 << 31)) or np.any(array >= (1 << 31)):
            raise OverflowError('INT32 accumulator overflow; no silent wrap')
        return array.astype(np.int32)

    def infer(self, image):
        image = np.asarray(image)
        if image.dtype != np.uint8 or image.shape not in ((64, 64), (1, 64, 64), (1, 1, 64, 64)):
            raise ValueError('Expected a single 64x64 uint8 input')
        x = image.reshape(1, 64, 64).astype(np.int64)
        layers = {'input_uint8': x[None].astype(np.uint8)}
        for i in range(1, self.manifest['num_conv_layers']+1):
            name = f'conv{i}'
            padded = np.pad(x, ((0, 0), (1, 1), (1, 1)))
            windows = np.lib.stride_tricks.sliding_window_view(padded, (3, 3), axis=(1, 2))
            channels, height, width, _, _ = windows.shape
            columns = windows.transpose(0, 3, 4, 1, 2).reshape(channels*9, height*width)
            weights = self.params[name+'_weight']
            acc = (weights.reshape(weights.shape[0], -1) @ columns).reshape(weights.shape[0], height, width)
            acc += self.params[name+'_bias'][:, None, None]
            layers[name+'_acc_int32'] = self.checked_int32(acc)[None]
            relu = rounded_q30(acc, self.manifest['layers'][name]['requant_multiplier_q30']).clip(0, 127)
            layers[name+'_relu_int8'] = relu[None].astype(np.int8)
            x = relu.reshape(relu.shape[0], height//2, 2, width//2, 2).max((2, 4))
            layers[f'pool{i}_int8'] = x[None].astype(np.int8)
        flat = x.reshape(-1)
        acc = self.params['fc1_weight'] @ flat + self.params['fc1_bias']
        layers['fc1_acc_int32'] = self.checked_int32(acc)[None]
        hidden = rounded_q30(acc, self.manifest['layers']['fc1']['requant_multiplier_q30']).clip(0, 127)
        layers['fc1_relu_int8'] = hidden[None].astype(np.int8)
        logits = self.params['fc2_weight'] @ hidden + self.params['fc2_bias']
        layers['fc2_logits_int32'] = self.checked_int32(logits)[None]
        return layers
