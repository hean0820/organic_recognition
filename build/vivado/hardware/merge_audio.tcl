# Camera bridge remains on M04; audio uses the new M05 port.
set_property CONFIG.NUM_MI {6} [get_bd_cells ps7_0_axi_periph]
create_bd_cell -type module -reference audio_axi audio_axi_0
set_property CONFIG.FIFO_BITS {12} [get_bd_cells audio_axi_0]
create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz:6.0 audio_clock
set_property -dict [list CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {12.000} CONFIG.PRIM_IN_FREQ {100.000} CONFIG.USE_LOCKED {true} CONFIG.USE_RESET {true}] [get_bd_cells audio_clock]
connect_bd_intf_net [get_bd_intf_pins ps7_0_axi_periph/M05_AXI] [get_bd_intf_pins audio_axi_0/s_axi]
foreach pin {ps7_0_axi_periph/M05_ACLK audio_axi_0/s_axi_aclk audio_clock/clk_in1} {
    tap processing_system7_0/FCLK_CLK0 $pin
}
foreach pin {ps7_0_axi_periph/M05_ARESETN audio_axi_0/s_axi_aresetn} {
    tap rst_ps7_0_100M/peripheral_aresetn $pin
}
tap rst_ps7_0_100M/peripheral_reset audio_clock/reset
tap audio_clock/locked audio_axi_0/clock_locked
foreach port {aud_bclk aud_lrc aud_adcdat voice_key_n} {
    create_bd_port -dir I $port
    connect_bd_net [get_bd_ports $port] [get_bd_pins audio_axi_0/$port]
}
foreach port {aud_dacdat aud_scl} {
    create_bd_port -dir O $port
    connect_bd_net [get_bd_ports $port] [get_bd_pins audio_axi_0/$port]
}
create_bd_port -dir IO aud_sda
connect_bd_net [get_bd_ports aud_sda] [get_bd_pins audio_axi_0/aud_sda]
create_bd_port -dir O -from 1 -to 0 voice_led
connect_bd_net [get_bd_ports voice_led] [get_bd_pins audio_axi_0/voice_led]
create_bd_port -dir O aud_mclk
connect_bd_net [get_bd_ports aud_mclk] [get_bd_pins audio_clock/clk_out1]
set regs [get_bd_addr_segs audio_axi_0/s_axi/*]
if {[llength $regs] != 1} {error "Ambiguous audio address segment"}
assign_bd_address -offset 0x43C30000 -range 64K -target_address_space [get_bd_addr_spaces processing_system7_0/Data] $regs -force
foreach {name address} {camera_bridge_ctrl 0x41200000 audio_axi_0 0x43C30000} {
    set seg [get_bd_addr_segs -quiet processing_system7_0/Data/SEG_${name}_*]
    if {[llength $seg] != 1 || [get_property OFFSET $seg] != $address} {error "Address mismatch: $name"}
}
