set here [file dirname [file normalize [info script]]]
set build [pwd]
if {[file exists "$build/project"]} {error "Refusing to overwrite HLS project"}
file mkdir $build
cd $build
open_project project
set_top prep_only_accel
add_files "$here/prep_accel.cpp" -cflags "-I$here"
open_solution solution1
set_part xc7z020clg400-2
create_clock -period 10.000 -name default
config_export -version 1.0 -vendor organic.local -library user -ipname prep_only_accel -description "Camera PREP only; modes0/1 preserved; no CNN compute" -format ip_catalog -rtl vhdl
csynth_design
if {[catch {export_design -format ip_catalog -rtl vhdl} detail]} {
    if {![file exists project/solution1/impl/ip/run_ippack.tcl]} {error $detail}
    puts "PREP_ONLY_HLS_GENERATED_REPACKAGE_FIXED_REVISION_REQUIRED"
}
exit
