set here [file dirname [file normalize [info script]]]
set baseline [file normalize "$here/baseline"]
if {[version -short] ne "2020.2"} {error "Use Vivado 2020.2"}
# A new output directory avoids reopening or editing the accepted project.
if {[llength $argv] > 1} {error "Usage: build_repro.tcl ?new_output_directory?"}
set output_root [file normalize "$here/../build_01"]
if {[llength $argv] == 1} {set output_root [file normalize [lindex $argv 0]]}
set project_dir "$output_root/project"
set output_dir "$output_root/output"
if {[file exists $project_dir] || [file exists $output_dir]} {
 error "Rebuild directories already exist; select a new output directory. Nothing was deleted."
}
source "$here/python_command.tcl"
set python_command [psv7_python_command]
file mkdir $output_dir
create_project camera_bridge $project_dir -part xc7z020clg400-2
if {![info exists ::s6_cnn_ip] || ![info exists ::s6_prep_ip]} {error "Provide packaged S6 CNN/PREP-only repositories via reproducible wrapper"}
set_property XPM_LIBRARIES {XPM_MEMORY} [current_project]
set_property ip_repo_paths [list $::s6_cnn_ip $::s6_prep_ip "$baseline/ip_repo"] [current_project]
config_ip_cache -disable_cache
update_ip_catalog
add_files -norecurse [list "$here/camera_bridge_control.v" "$here/camera_signal_monitor.v"]
add_files -norecurse [glob "$here/audio/*.v" "$here/audio/*.vh"]
set_property include_dirs [list "$here/audio"] [current_fileset]
if {[llength [get_files -quiet */system.bd]] == 0} {
 import_files -norecurse "$baseline/ov5640_hdmi.srcs/sources_1/bd/system/system.bd"
}
set bd [get_files */system.bd]
open_bd_design $bd
source "$here/integrate_unified.tcl"
create_bd_cell -type module -reference camera_bridge_reset_gate bridge_control_0
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 camera_bridge_ctrl
set_property -dict [list CONFIG.C_GPIO_WIDTH {2} CONFIG.C_ALL_OUTPUTS {1} \
 CONFIG.C_DOUT_DEFAULT {0x00000000} CONFIG.C_IS_DUAL {1} CONFIG.C_GPIO2_WIDTH {6} \
 CONFIG.C_ALL_INPUTS_2 {1} CONFIG.C_INTERRUPT_PRESENT {0}] [get_bd_cells camera_bridge_ctrl]
set_property CONFIG.NUM_MI {5} [get_bd_cells ps7_0_axi_periph]
connect_bd_intf_net [get_bd_intf_pins ps7_0_axi_periph/M04_AXI] [get_bd_intf_pins camera_bridge_ctrl/S_AXI]
proc tap {source sink} {connect_bd_net [get_bd_pins $source] [get_bd_pins $sink]}
foreach pin {ps7_0_axi_periph/M04_ACLK camera_bridge_ctrl/s_axi_aclk bridge_control_0/clk} {
 tap processing_system7_0/FCLK_CLK0 $pin
}
foreach pin {ps7_0_axi_periph/M04_ARESETN camera_bridge_ctrl/s_axi_aresetn bridge_control_0/ps_resetn} {
 tap rst_ps7_0_100M/peripheral_aresetn $pin
}
tap clk_wiz_0/locked bridge_control_0/locked
connect_bd_net [get_bd_ports cam_pclk] [get_bd_pins bridge_control_0/cam_pclk]
tap camera_bridge_ctrl/gpio_io_o bridge_control_0/ctrl
tap bridge_control_0/status camera_bridge_ctrl/gpio2_io_i
tap v_vid_in_axi4s_0/overflow bridge_control_0/overflow
tap v_vid_in_axi4s_0/underflow bridge_control_0/underflow
foreach {output input} {
 bridge_aresetn aresetn
 native_hold vid_io_in_reset
 bridge_axis_enable axis_enable
} {
 set dest [get_bd_pins v_vid_in_axi4s_0/$input]
 set old_nets [get_bd_nets -quiet -of_objects $dest]
 if {[llength $old_nets] != 0} {disconnect_bd_net $old_nets $dest}
 tap bridge_control_0/$output v_vid_in_axi4s_0/$input
}
assign_bd_address -offset 0x41200000 -range 64K [get_bd_addr_segs camera_bridge_ctrl/S_AXI/Reg]
create_bd_cell -type module -reference camera_signal_monitor camera_monitor_0
create_bd_cell -type ip -vlnv xilinx.com:ip:ila:6.2 ila_camera_path
set_property CONFIG.C_MONITOR_TYPE {Native} [get_bd_cells ila_camera_path]
set_property -dict [list CONFIG.C_NUM_OF_PROBES {8} CONFIG.C_DATA_DEPTH {1024} \
 CONFIG.C_PROBE0_WIDTH {16} CONFIG.C_PROBE1_WIDTH {32} CONFIG.C_PROBE2_WIDTH {32} \
 CONFIG.C_PROBE3_WIDTH {32} CONFIG.C_PROBE4_WIDTH {32} CONFIG.C_PROBE5_WIDTH {32} \
 CONFIG.C_PROBE6_WIDTH {32} CONFIG.C_PROBE7_WIDTH {32}] [get_bd_cells ila_camera_path]
tap processing_system7_0/FCLK_CLK0 camera_monitor_0/clk
tap processing_system7_0/FCLK_CLK0 ila_camera_path/clk
foreach port {cam_pclk cam_vsync cam_href} {
 connect_bd_net [get_bd_ports $port] [get_bd_pins camera_monitor_0/$port]
}
foreach {source destination} {
 clk_wiz_0/locked locked
 rst_ps7_0_100M/peripheral_aresetn video_resetn
 ov5640_capture_data_0/cmos_frame_ce cmos_ce
 ov5640_capture_data_0/cmos_frame_vsync cmos_vsync
 ov5640_capture_data_0/cmos_active_video cmos_active
 v_vid_in_axi4s_0/m_axis_video_tvalid tvalid
 v_vid_in_axi4s_0/m_axis_video_tready tready
 v_vid_in_axi4s_0/m_axis_video_tuser tuser
 v_vid_in_axi4s_0/m_axis_video_tlast tlast
 v_vid_in_axi4s_0/overflow bridge_overflow
 v_vid_in_axi4s_0/underflow bridge_underflow
 bridge_control_0/bridge_aresetn bridge_aresetn
 bridge_control_0/bridge_axis_enable bridge_axis_enable
} {tap $source camera_monitor_0/$destination}
foreach {source sink} {
 ov5640_capture_data_0/cmos_frame_vsync v_vid_in_axi4s_0/vid_vsync
 ov5640_capture_data_0/cmos_active_video v_vid_in_axi4s_0/vid_active_video
 v_vid_in_axi4s_0/m_axis_video_tvalid axi_vdma_0/s_axis_s2mm_tvalid
 v_vid_in_axi4s_0/m_axis_video_tuser axi_vdma_0/s_axis_s2mm_tuser
 v_vid_in_axi4s_0/m_axis_video_tlast axi_vdma_0/s_axis_s2mm_tlast
 axi_vdma_0/s_axis_s2mm_tready v_vid_in_axi4s_0/m_axis_video_tready
} {tap $source $sink}
set index 0
foreach signal {flags heartbeat pclk_activity raw_events cmos_events axis_beats axis_events axis_stalls} {
 tap camera_monitor_0/$signal ila_camera_path/probe$index
 incr index
}
source "$here/merge_audio.tcl"
validate_bd_design
save_bd_design
generate_target all $bd
exec {*}$python_command -I "$here/audit.py" --baseline-netlist "$baseline/system_reference.v" --generated-netlist "$project_dir/camera_bridge.gen/sources_1/bd/system/synth/system.v" --report "$output_dir/connection_audit.json"
add_files -norecurse [make_wrapper -files $bd -top]
add_files -fileset constrs_1 -norecurse [list "$baseline/design/ov5640_lcd.xdc" "$here/debug_cdc.xdc" "$here/audio/audio.xdc"]
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
write_bd_tcl -force "$output_dir/system_recreate.tcl"
if {[info exists ::s6_integration_only] && $::s6_integration_only} {
 puts "S6_BD_OUTPUT_PRODUCTS_PASS"
 close_project
 exit
}
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "Synthesis failed"}
open_run synth_1
report_utilization -hierarchical -file "$output_dir/synthesis_utilization_hierarchical.rpt"
report_utilization -file "$output_dir/synthesis_utilization.rpt"
close_design
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Implementation failed"}
open_run impl_1
file mkdir $output_dir
report_timing_summary -file "$output_dir/timing_summary.rpt"
report_bus_skew -file "$output_dir/bus_skew.rpt"
report_cdc -file "$output_dir/cdc.rpt"
check_timing -verbose -file "$output_dir/check_timing.rpt"
report_clock_interaction -file "$output_dir/clock_interaction.rpt"
report_utilization -file "$output_dir/utilization.rpt"
report_utilization -hierarchical -file "$output_dir/utilization_hierarchical.rpt"
report_drc -file "$output_dir/drc.rpt"
source "$here/check_hardware.tcl"
set ::s7_audit_phase routed
source "$here/audit_s7_netlist.tcl"
write_checkpoint "$output_dir/system_routed.dcp"
write_hw_platform -fixed -force -include_bit -file "$output_dir/camera_audio.xsa"
write_debug_probes -force "$output_dir/psv7_camera_audio.ltx"
file copy -force "$project_dir/camera_bridge.runs/impl_1/system_wrapper.bit" "$output_dir/psv7_camera_audio.bit"
file copy -force "$project_dir/camera_bridge.gen/sources_1/bd/system/hw_handoff/system.hwh" "$output_dir/psv7_camera_audio.hwh"
puts "CAMERA_AUDIO_BUILD_FINISHED"
