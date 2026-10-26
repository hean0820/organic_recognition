"""Explicit project resources and the supported board profile; no device access."""
import hashlib
import json
import platform
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EDITABLE_NOTEBOOKS = ('notebooks/01_application.ipynb', 'notebooks/02_entry_validation.ipynb')
ACCEPTED_CAMERA_HANDOFF = 'OVERLAP_SECOND_EVENT_WITH_PARK'


def check_notebook(file):
    """Jupyter updates outputs/metadata/source; validate format, not byte identity."""
    notebook = json.loads(file.read_text(encoding='utf-8'))
    if notebook.get('nbformat') != 4 or not isinstance(notebook.get('cells'), list):
        raise ValueError('Invalid operation Notebook: ' + str(file))
    for cell in notebook['cells']:
        if cell.get('cell_type') not in ('code', 'markdown', 'raw'):
            raise ValueError('Invalid Notebook cell type: ' + str(file))
        source = cell.get('source')
        if not isinstance(source, str) and not (isinstance(source, list) and all(isinstance(line, str) for line in source)):
            raise ValueError('Invalid Notebook cell source: ' + str(file))


def load_config(root=None):
    root = Path(root).resolve() if root else Path(__file__).resolve().parents[1]
    config = json.loads((root / 'project.json').read_text(encoding='utf-8'))
    from .bootstrap import IP_ADDRESSES
    if config['ip_addresses'] != IP_ADDRESSES or config['ps_reference_mhz'] != 33.333333 or config['fclk_mhz'] != 100.0:
        raise ValueError('This application supports only the frozen navigator camera hardware profile')
    if config.get('audio_enabled') is not True or config.get('audio_contract') != {'id':0x41554432,'version':65536,'rate_hz':16000,'fifo_depth':4096,'channels':1,'width_bytes':2}:
        raise ValueError('Audio configuration differs from the reviewed hardware contract')
    if config['voice_enabled'] is not True or config.get('voice_model_version') != 'chem22_real4_v1_candidate' or config['overlay_directory'] != 'overlay':
        raise ValueError('This candidate requires the frozen stage2 voice model and paired audio Overlay')
    if config.get('camera_handoff_default') != ACCEPTED_CAMERA_HANDOFF:
        raise ValueError('Formal entry requires the reviewed OVERLAP_SECOND_EVENT_WITH_PARK recognition policy')
    if config.get('runtime_fclk1_mhz')!=config['fclk_mhz'] or config.get('hardware_metadata_fclk1_mhz')!=150.0:
        raise ValueError('Clock policy mismatch: qualified 100/150 MHz, preserved runtime 100/100 MHz')
    return root, config


def verify_speed_hwh(root, config):
    if config.get('unified_cnn_enabled') is not True or config.get('speed_fc_enabled') is not False:
        raise ValueError('This application requires unified RTL CNN and PREP-only')
    tree=ET.parse(root/'overlay/psv7.hwh')
    core=next((m for m in tree.iter('MODULE') if m.get('INSTANCE')=='prep_accel_0'),None)
    if core is None or core.get('COREREVISION')!='1000000001' or core.get('VLNV')!='organic.local:user:prep_only_accel:1.0':
        raise RuntimeError('PREP-only IP identity/revision mismatch')
    cnn=next((m for m in tree.iter('MODULE') if m.get('INSTANCE')=='cnn_ps_if_0'),None)
    if cnn is None or cnn.get('VLNV')!='organic.local:user:cnn_rtl_unified:1.0' or cnn.get('COREREVISION')!='1000000001':
        raise RuntimeError('Unified CNN IP identity mismatch')
    ps=next((m for m in tree.iter('MODULE') if m.get('INSTANCE')=='processing_system7_0'),None)
    clock_params={p.get('NAME'):p.get('VALUE') for p in ps.iter('PARAMETER')} if ps is not None else {}
    expected_clocks={'PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ':100.0,'PCW_ACT_FPGA1_PERIPHERAL_FREQMHZ':config['hardware_metadata_fclk1_mhz']}
    if any(abs(float(clock_params.get(k,0))-v)>0.01 for k,v in expected_clocks.items()):
        raise RuntimeError('HWH qualification clock configuration mismatch')
    expected={'CTRL':0,'ap_return':0x10,'frame_1':0x18,'frame_2':0x1c,
              'detection_1':0x24,'detection_2':0x28,'gray_1':0x30,'gray_2':0x34,
              'horizontal_1':0x3c,'horizontal_2':0x40,'ink_1':0x48,'ink_2':0x4c,
              'stride_words':0x54,'mode':0x5c}
    registers={r.get('NAME'):int(next(p.get('VALUE') for p in r.findall('PROPERTY') if p.get('NAME')=='ADDRESS_OFFSET'),0)
               for r in core.iter('REGISTER')}
    if any(registers.get(name)!=offset for name,offset in expected.items()):
        raise RuntimeError('PREP-only control register map differs from the reviewed driver')
    ranges={r.get('INSTANCE'):int(r.get('BASEVALUE'),0) for r in tree.iter('MEMRANGE')}
    if any(ranges.get(name)!=address for name,address in config['ip_addresses'].items()):
        raise RuntimeError('Unified CNN/PREP-only paired HWH address mismatch')
    return len(expected)


def verify_project(root=None):
    root, config = load_config(root)
    if not config.get('offline_hardware_build_ready'):
        raise RuntimeError('S6 integration has no paired routed bitstream; finish S7 before deployment')
    manifest = json.loads((root / 'release_manifest.json').read_text(encoding='utf-8'))
    checked = 0
    for name, expected in manifest['sha256'].items():
        file = (root / name).resolve()
        if root not in file.parents or not file.is_file():
            raise FileNotFoundError('Missing or invalid package member: ' + name)
        if name in EDITABLE_NOTEBOOKS:
            # Also accepts the previous release manifest, which listed the
            # editable Notebook among immutable files. Never skip runtime code.
            continue
        if hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise RuntimeError('Package hash mismatch: ' + name)
        checked += 1
    for name in EDITABLE_NOTEBOOKS:
        file = (root / name).resolve()
        if root not in file.parents or not file.is_file():
            raise FileNotFoundError('Operation Notebook missing or outside project: ' + name)
        check_notebook(file)
    for name, expected in config['sha256'].items():
        file = root / ('overlay' if name.endswith(('.bit', '.hwh')) else 'assets') / name
        if hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise RuntimeError('Frozen hardware/model identity mismatch: ' + name)
    register_count=verify_speed_hwh(root,config)
    return {'package_files_checked': checked,
            'editable_notebooks_checked': len(EDITABLE_NOTEBOOKS),
            'version': config['project_version'], 'hardware_accessed': False,
            'formal_board_acceptance': config['formal_board_acceptance'],
            'speed_hwh_registers_checked':register_count}


def check_environment(config):
    import pynq
    import numpy
    observed = {'pynq': pynq.__version__, 'numpy': numpy.__version__,
                'python': platform.python_version(), 'machine': platform.machine(),
                'gcc': shutil.which('gcc')}
    if observed['pynq'] != config['pynq_version'] or observed['machine'] != config['machine']:
        raise RuntimeError('Unsupported board runtime: ' + repr(observed))
    if sys.version_info < (3, 8) or not observed['gcc']:
        raise RuntimeError('Python >=3.8 and board GCC are required: ' + repr(observed))
    return observed
