# Only monitor and controller status sampling cross these domains.
set_false_path -to [get_pins -hierarchical -filter {NAME =~ */camera_monitor_0/inst/sync1_reg*/D}]
set_false_path -to [get_pins -hierarchical -filter {NAME =~ */camera_monitor_0/inst/error_sync1_reg*/D}]
set_false_path -to [get_pins -hierarchical -filter {NAME =~ */bridge_control_0/inst/status_sync1_reg*/D}]
# GPIO release request is from FCLK, synchronized into the PCLK domain.
# Do not relax the video data paths or the release shift-register stages.
set_false_path -to [get_pins -hierarchical -filter {NAME =~ */bridge_control_0/inst/vid_request_sync1_reg/D}]
set_false_path -to [get_pins -hierarchical -filter {NAME =~ */bridge_control_0/inst/vid_enable_sync1_reg/D}]
