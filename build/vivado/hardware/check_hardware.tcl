# Only export a candidate after timing and DRC reports have been reviewed by gates.
set setup [get_timing_paths -delay_type max -max_paths 1]
set hold [get_timing_paths -delay_type min -max_paths 1]
if {![llength $setup] || ![llength $hold]} {error "Missing timing paths"}
set wns [get_property SLACK $setup]
set whs [get_property SLACK $hold]
if {$wns < 0 || $whs < 0} {error "Camera/audio timing failed: WNS=$wns WHS=$whs"}
set violations [get_drc_violations -quiet -filter {SEVERITY == "Error" || SEVERITY == "Critical Warning"}]
if {[llength $violations]} {error "DRC errors/critical warnings: $violations"}
set timing_file [open "$output_dir/check_timing.rpt" r]
set timing_text [read $timing_file]
close $timing_file
foreach name {no_clock unconstrained_internal_endpoints multiple_clock generated_clocks loops partial_input_delay partial_output_delay latch_loops} {
    # Braces avoid Tcl interpreting the regex character class as a command.
    set pattern [format {checking %s \(([0-9]+)\)} $name]
    if {![regexp $pattern $timing_text ignored count] || $count != 0} {
        error "Timing coverage check failed: $name"
    }
}
set f [open "$output_dir/build_result.json" w]
puts $f "{\"timing_passed\":true,\"wns_ns\":$wns,\"whs_ns\":$whs,\"drc_error_or_critical_count\":0,\"internal_clock_and_constraint_checks\":\"passed\",\"board_verified\":false}"
close $f
