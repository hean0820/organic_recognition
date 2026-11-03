# 完整整机网表核查；共享缓存必须各一份，旧HLS CNN和旧输出RAM不得残留。
set bb [get_cells -quiet -hier -filter {IS_BLACKBOX == 1}]
if {[llength $bb]} {error "S7 black boxes remain: $bb"}
set old [get_cells -quiet -hier -filter {NAME =~ *speed_fc_kernel* || NAME =~ *cnn_axi_buffer* || NAME =~ *cnn_output_bram* || REF_NAME =~ cnn_conv3_subsystem* || REF_NAME =~ cnn_fc_subsystem*}]
if {[llength $old]} {error "S7 obsolete or duplicate compute hierarchy: $old"}
set fp [open "$output_dir/${::s7_audit_phase}_hierarchy_instances.tsv" w]
puts $fp "NAME\tREF_NAME\tORIG_REF_NAME"
foreach c [get_cells -hier -filter {IS_PRIMITIVE == 0}] {
 puts $fp "[get_property NAME $c]\t[get_property REF_NAME $c]\t[get_property ORIG_REF_NAME $c]"
}
close $fp
foreach suffix {core/pool2 core/pool3 core/quant core/loader core/c3 core/fc} {
 set cells [get_cells -quiet -hier -filter "NAME =~ *cnn_ps_if_0/inst/$suffix"]
 if {[llength $cells] != 1} {error "S7 expected one $suffix; found: $cells"}
}
set fp [open "$output_dir/${::s7_audit_phase}_memory_dsp.tsv" w]
puts $fp "NAME\tREF_NAME"
foreach c [get_cells -hier -filter {REF_NAME =~ RAMB* || REF_NAME =~ DSP48*}] {puts $fp "[get_property NAME $c]\t[get_property REF_NAME $c]"}
close $fp
report_clocks -file "$output_dir/${::s7_audit_phase}_clocks.rpt"
puts "S7_${::s7_audit_phase}_NETLIST_AUDIT_PASS"
