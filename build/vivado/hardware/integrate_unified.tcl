# S6只替换CNN与PREP单元；视频/音频地址、HP0及原时钟复位保持原工程。
proc restore_pin_net {net pin} {connect_bd_net -net $net [get_bd_pins $pin]}
set cnn_ctrl [get_bd_intf_nets -of_objects [get_bd_intf_pins cnn_ps_if_0/S_AXI]]
set cnn_clk [get_bd_nets -of_objects [get_bd_pins cnn_ps_if_0/s_axi_aclk]]
set cnn_rst [get_bd_nets -of_objects [get_bd_pins cnn_ps_if_0/s_axi_aresetn]]
set prep_ctrl [get_bd_intf_nets -of_objects [get_bd_intf_pins prep_accel_0/s_axi_control]]
set prep_mem [get_bd_intf_nets -of_objects [get_bd_intf_pins prep_accel_0/m_axi_gmem]]
set prep_clk [get_bd_nets -of_objects [get_bd_pins prep_accel_0/ap_clk]]
set prep_rst [get_bd_nets -of_objects [get_bd_pins prep_accel_0/ap_rst_n]]
delete_bd_objs [get_bd_cells cnn_ps_if_0] [get_bd_cells prep_accel_0]
create_bd_cell -type ip -vlnv organic.local:user:cnn_rtl_unified:1.0 cnn_ps_if_0
create_bd_cell -type ip -vlnv organic.local:user:prep_only_accel:1.0 prep_accel_0
connect_bd_intf_net -intf_net $cnn_ctrl [get_bd_intf_pins ps7_0_axi_periph/M02_AXI] [get_bd_intf_pins cnn_ps_if_0/S_AXI_CONTROL]
connect_bd_intf_net -intf_net $prep_ctrl [get_bd_intf_pins ps7_0_axi_periph/M03_AXI] [get_bd_intf_pins prep_accel_0/s_axi_control]
connect_bd_intf_net -intf_net $prep_mem [get_bd_intf_pins prep_regslice/S_AXI] [get_bd_intf_pins prep_accel_0/m_axi_gmem]
restore_pin_net $cnn_clk cnn_ps_if_0/clk
restore_pin_net $cnn_rst cnn_ps_if_0/resetn
restore_pin_net $prep_clk prep_accel_0/ap_clk
restore_pin_net $prep_rst prep_accel_0/ap_rst_n
set_property -dict [list CONFIG.NUM_SI {2} CONFIG.NUM_MI {1} CONFIG.XBAR_DATA_WIDTH {64}] [get_bd_cells prep_mem_intercon]
connect_bd_intf_net [get_bd_intf_pins cnn_ps_if_0/M_AXI_MODEL_READ] [get_bd_intf_pins prep_mem_intercon/S01_AXI]
restore_pin_net $cnn_clk prep_mem_intercon/S01_ACLK
restore_pin_net $cnn_rst prep_mem_intercon/S01_ARESETN
assign_bd_address -offset 0x43C00000 -range 64K -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs cnn_ps_if_0/S_AXI_CONTROL/registers] -force
assign_bd_address -offset 0x43C20000 -range 64K -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs prep_accel_0/s_axi_control/Reg] -force
foreach space {prep_accel_0/Data_m_axi_gmem cnn_ps_if_0/M_AXI_MODEL_READ} {
 assign_bd_address -offset 0 -range 1G -target_address_space [get_bd_addr_spaces $space] [get_bd_addr_segs processing_system7_0/S_AXI_HP1/HP1_DDR_LOWOCM] -force
}
puts "S6_UNIFIED_BD_CONNECTED"
