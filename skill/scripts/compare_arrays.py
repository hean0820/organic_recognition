"""Compare matching NPY/NPZ keys, shape, dtype and every element exactly."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np


def load(path):
    value = np.load(path, allow_pickle=False)
    if isinstance(value, np.lib.npyio.NpzFile):
        with value:
            return {key: value[key].copy() for key in value.files}
    return {'array': value}


def compare(expected, actual):
    reference, observed = load(expected), load(actual)
    if reference.keys() != observed.keys():
        raise ValueError('Archive keys differ')
    result = {}
    for key in sorted(reference):
        left, right = reference[key], observed[key]
        if left.shape != right.shape or left.dtype != right.dtype:
            raise ValueError('Shape or dtype differs: ' + key)
        result[key] = int(np.count_nonzero(left != right))
    return {'passed': not any(result.values()), 'kind': 'exact_saved_array_comparison',
            'differences': result, 'source_sha256': {
                'expected': hashlib.sha256(Path(expected).read_bytes()).hexdigest(),
                'actual': hashlib.sha256(Path(actual).read_bytes()).hexdigest()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('expected', type=Path)
    parser.add_argument('actual', type=Path)
    args = parser.parse_args()
    try:
        result = compare(args.expected, args.actual)
    except Exception as error:
        result = {'passed': False, 'error': str(error)}
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
