"""Compile the exact formal native sources; Windows output is host evidence only."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNITS = ['native_wrapper.c', 'preview_compose.c', 'ui_panel.c', 'ui_font.c', 'chem_db.c',
         'preprocess.c', 'cnn_fc.c', 'app_control.c', 'ui_font_extra.c', 'mol_render.c',
         'mol_selection.c', 'mol_board.c', 'molecule_models.c',
         'chem22.c', 'voice_capture.c', 'voice_recognizer.c', 'voice_bridge.c', 'cnn_mmio.c', 'frame_copy.c', 'preprocess_reference.c']


def build():
    sources = ROOT / 'native'
    inputs=[p for p in sorted(sources.iterdir()) if p.suffix in ('.c','.h')]
    inputs.append(ROOT/'assets/camera_pipeline_reference/preprocess_0_7_0.c')
    digest = hashlib.sha256(b''.join(p.read_bytes() for p in inputs)).hexdigest()
    folder = ROOT / 'reports/native'
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / ('libpsv7_ui_' + digest + ('.dll' if os.name == 'nt' else '.so'))
    if output.exists():
        print('NATIVE_CACHED',output)
        return output
    temporary = output.with_suffix(output.suffix + '.building')
    command = ['gcc', '-O2', '-std=c99', '-Wall', '-Wextra', '-Werror', '-D_POSIX_C_SOURCE=200809L', '-shared']
    if os.name != 'nt':
        command.append('-fPIC')
    command += ['-I', str(sources), '-o', str(temporary)] + [str(sources / name) for name in UNITS] + ['-lm']
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if result.returncode:
        raise RuntimeError(result.stderr)
    temporary.replace(output)
    print('NATIVE_COMPILED', output, 'host_only' if os.name == 'nt' else 'inspect target architecture')
    return output


if __name__ == '__main__':
    build()
