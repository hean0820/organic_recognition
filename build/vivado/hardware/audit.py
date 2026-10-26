import json
import re
import argparse
from pathlib import Path
root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description='Audit baseline and rebuilt camera bridge wiring')
parser.add_argument('--baseline-netlist',type=Path,default=root.parent/'stage1/ov5640_hdmi.gen/sources_1/bd/system/synth/system.v')
parser.add_argument('--generated-netlist',type=Path,default=root/'build/camera_bridge.gen/sources_1/bd/system/synth/system.v')
parser.add_argument('--report',type=Path,default=root/'connection_audit.json')
args=parser.parse_args()
original = args.baseline_netlist.read_text()
new = args.generated_netlist.read_text()
def cell(text, name):
    found = re.search(r'\b\w+\s+' + re.escape(name) + r'\s*\((.*?)\);', text, re.S)
    assert found, name
    return dict(re.findall(r'\.(\w+)\(([^()]*)\)', found.group(1)))
pairs = [('ov5640_capture_data_0','cmos_active_video','v_vid_in_axi4s_0','vid_active_video'),
         ('ov5640_capture_data_0','cmos_frame_vsync','v_vid_in_axi4s_0','vid_vsync'),
         ('ov5640_capture_data_0','cmos_frame_data','v_vid_in_axi4s_0','vid_data'),
         ('ov5640_capture_data_0','cmos_frame_clk','v_vid_in_axi4s_0','vid_io_in_clk'),
         ('ov5640_capture_data_0','cmos_frame_ce','v_vid_in_axi4s_0','vid_io_in_ce'),
         ('clk_wiz_0','locked','ov5640_capture_data_0','rst_n'),
         ('processing_system7_0','FCLK_CLK0','axi_vdma_0','s_axis_s2mm_aclk'),
         ('processing_system7_0','FCLK_CLK0','v_vid_in_axi4s_0','aclk')]
for signal in ('tdata','tvalid','tready','tuser','tlast'):
    pairs.append(('v_vid_in_axi4s_0','m_axis_video_'+signal,'axi_vdma_0','s_axis_s2mm_'+signal))
for text in (original, new):
    for a, ap, b, bp in pairs:
        assert cell(text,a)[ap] == cell(text,b)[bp], (a,ap,b,bp)
control = cell(new,'bridge_control_0')
bridge = cell(new,'v_vid_in_axi4s_0')
for source, sink in (('bridge_aresetn','aresetn'), ('native_hold','vid_io_in_reset'),
                     ('bridge_axis_enable','axis_enable')):
    assert control[source] == bridge[sink], (source, sink)
assert control['ctrl'] == cell(new,'camera_bridge_ctrl')['gpio_io_o']
assert control['status'] == cell(new,'camera_bridge_ctrl')['gpio2_io_i']
monitor = cell(new,'camera_monitor_0')
for src,dst in (('overflow','bridge_overflow'),('underflow','bridge_underflow')):
    assert monitor[dst] == bridge[src]
ila = cell(new,'ila_camera_path')
for i, signal in enumerate(('flags','heartbeat','pclk_activity','raw_events','cmos_events','axis_beats','axis_events','axis_stalls')):
    assert ila['probe'+str(i)] == monitor[signal]
result = {'result':'PASS','original_connections_checked':len(pairs),
          'controlled_reset_enable_connections':3,'ila_probes':8,'bridge_status_control':'PASS'}
args.report.parent.mkdir(parents=True,exist_ok=True)
args.report.write_text(json.dumps(result,indent=2))
print(json.dumps(result))
