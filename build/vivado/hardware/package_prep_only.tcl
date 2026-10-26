# 2020.2 date revision overflows signed INT32. Scope this workaround to packaging.
if {[llength $argv] != 1} {error "Usage: package_prep_only.tcl generated_ip_directory"}
cd [file normalize [lindex $argv 0]]
proc prep_revision {name element operation} {upvar #0 $name v; set v 1000000001}
proc prep_vendor {name element operation} {upvar #0 $name v; set v organic.local}
proc prep_library {name element operation} {upvar #0 $name v; set v user}
trace add variable ::Revision write prep_revision
trace add variable ::Vendor write prep_vendor
trace add variable ::Library write prep_library
source -notrace run_ippack.tcl
puts "PREP_ONLY_PACKAGE_PASS_REVISION_1000000001"
exit
