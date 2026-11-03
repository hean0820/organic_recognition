set here [file dirname [file normalize [info script]]]
set output_root [file normalize "$here/../build_02"]
set project_dir "$output_root/project"
set output_dir "$output_root/output"
if {[version -short] ne "2020.2"} {error "Use Vivado 2020.2"}
open_project "$project_dir/camera_bridge.xpr"
foreach run [get_runs -filter {IS_SYNTHESIS == 1}] {
    if {[get_property PROGRESS $run] ne "100%"} {reset_run $run}
}
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {
    launch_runs synth_1 -jobs 4
    wait_on_run synth_1
}
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "Synthesis failed"}
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {
    launch_runs impl_1 -to_step write_bitstream -jobs 4
    wait_on_run impl_1
}
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Implementation failed"}
open_run impl_1
report_timing_summary -file "$output_dir/timing_summary.rpt"
report_bus_skew -file "$output_dir/bus_skew.rpt"
report_cdc -file "$output_dir/cdc.rpt"
check_timing -verbose -file "$output_dir/check_timing.rpt"
report_clock_interaction -file "$output_dir/clock_interaction.rpt"
report_utilization -file "$output_dir/utilization.rpt"
report_drc -file "$output_dir/drc.rpt"
source "$here/check_hardware.tcl"
write_hw_platform -fixed -force -include_bit -file "$output_dir/camera_audio.xsa"
write_debug_probes -force "$output_dir/psv7_camera_audio.ltx"
file copy -force "$project_dir/camera_bridge.runs/impl_1/system_wrapper.bit" "$output_dir/psv7_camera_audio.bit"
file copy -force "$project_dir/camera_bridge.gen/sources_1/bd/system/hw_handoff/system.hwh" "$output_dir/psv7_camera_audio.hwh"
puts "CAMERA_AUDIO_BUILD_FINISHED"
close_project
exit
