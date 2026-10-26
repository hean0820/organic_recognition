#----------------------摄像头接口的时钟---------------------------
#72M
create_clock -period 13.888 -name cam_pclk [get_ports cam_pclk]
set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets cam_pclk_IBUF]

#HDMI
set_property -dict {PACKAGE_PIN J20  IOSTANDARD TMDS_33 } [get_ports {TMDS_0_tmds_data_p[2]}]
set_property -dict {PACKAGE_PIN K19  IOSTANDARD TMDS_33 } [get_ports {TMDS_0_tmds_data_p[1]}]
set_property -dict {PACKAGE_PIN G19  IOSTANDARD TMDS_33 } [get_ports {TMDS_0_tmds_data_p[0]}]
set_property -dict {PACKAGE_PIN J18  IOSTANDARD TMDS_33 } [get_ports  TMDS_0_tmds_clk_p]



#----------------------摄像头接口---------------------------
set_property -dict {PACKAGE_PIN P14 IOSTANDARD LVCMOS33} [get_ports cam_rst_n]
set_property -dict {PACKAGE_PIN V15 IOSTANDARD LVCMOS33} [get_ports cam_pwdn]
set_property -dict {PACKAGE_PIN R14 IOSTANDARD LVCMOS33} [get_ports {cam_data[0]}]
set_property -dict {PACKAGE_PIN U13 IOSTANDARD LVCMOS33} [get_ports {cam_data[1]}]
set_property -dict {PACKAGE_PIN V13 IOSTANDARD LVCMOS33} [get_ports {cam_data[2]}]
set_property -dict {PACKAGE_PIN U15 IOSTANDARD LVCMOS33} [get_ports {cam_data[3]}]
set_property -dict {PACKAGE_PIN U14 IOSTANDARD LVCMOS33} [get_ports {cam_data[4]}]
set_property -dict {PACKAGE_PIN W13 IOSTANDARD LVCMOS33} [get_ports {cam_data[5]}]
set_property -dict {PACKAGE_PIN V12 IOSTANDARD LVCMOS33} [get_ports {cam_data[6]}]
set_property -dict {PACKAGE_PIN Y14 IOSTANDARD LVCMOS33} [get_ports {cam_data[7]}]
set_property -dict {PACKAGE_PIN T12 IOSTANDARD LVCMOS33} [get_ports cam_href]
set_property -dict {PACKAGE_PIN W14 IOSTANDARD LVCMOS33} [get_ports cam_pclk]
set_property -dict {PACKAGE_PIN U12 IOSTANDARD LVCMOS33} [get_ports cam_vsync]
#cam_scl:
set_property -dict {PACKAGE_PIN T10 IOSTANDARD LVCMOS33} [get_ports {emio_sccb_tri_io[0]}]
#cam_sda:
set_property -dict {PACKAGE_PIN T11 IOSTANDARD LVCMOS33} [get_ports {emio_sccb_tri_io[1]}]

set_property PULLUP true [get_ports {emio_sccb_tri_io[1]}]

