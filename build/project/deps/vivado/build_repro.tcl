# Rebuild only when intentionally changing hardware; output must be new.
set root [file dirname [file normalize [info script]]]
if {[llength $argv] != 1} {error "Usage: vivado -mode batch -source build_repro.tcl -tclargs NEW_OUTPUT_DIRECTORY"}
set ::s6_integration_only 0
set ::s6_cnn_ip "$root/ip_repo/cnn_rtl_unified"
set ::s6_prep_ip "$root/ip_repo/prep_only_accel"
source "$root/hardware/build_optimized.tcl"
