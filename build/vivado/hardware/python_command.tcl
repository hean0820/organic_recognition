# Select Python without embedding a workstation-specific installation path.
proc psv7_python_command {} {
    set candidates {}
    if {[info exists ::env(PSV7_PYTHON)] && $::env(PSV7_PYTHON) ne ""} {
        lappend candidates [list $::env(PSV7_PYTHON)]
    } else {
        foreach name {python3 python} {
            set command [auto_execok $name]
            if {$command ne ""} {lappend candidates $command}
        }
    }
    foreach command $candidates {
        if {![catch {exec {*}$command -c {import sys; assert sys.version_info >= (3,8); print("PSV7_PYTHON_READY")}} result]} {
            if {[string trim $result] eq "PSV7_PYTHON_READY"} {return $command}
        }
    }
    error "Python3.8+ not available. Set PSV7_PYTHON to the full interpreter path before starting Vivado."
}
