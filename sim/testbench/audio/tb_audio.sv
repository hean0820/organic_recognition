`timescale 1ns/1ps
module tb_audio;
 reg clk=0, resetn=0, lr=0, serial=0;
 wire valid;wire [23:0] sample;
 audio_receive #(.WL(24)) dut(.rst_n(resetn),.aud_bclk(clk),.aud_lrc(lr),.aud_adcdat(serial),.rx_done(valid),.adc_data(sample));
 always #5 clk=~clk;
 reg fir_valid=0; wire pcm_valid,overrun; wire signed [15:0] pcm;
 fir_decimate3 fir(.clk(clk),.rst_n(resetn),.valid_in(fir_valid),.sample_in(16'sd16384),.valid_out(pcm_valid),.sample_out(pcm),.overrun(overrun));
 integer pcm_count=0;
 always @(negedge clk) if(pcm_valid) begin
   if(pcm !== (pcm_count==0 ? 16'sd3 : -16'sd7)) $fatal(1,"PCM mismatch sample %d value %d",pcm_count,pcm);
   pcm_count=pcm_count+1;
 end
 task send_word(input [23:0] expected);integer bit_index;begin
  @(negedge clk);lr=~lr;
  for(bit_index=23;bit_index>=0;bit_index=bit_index-1)begin
    @(negedge clk);serial=expected[bit_index];
  end
  @(negedge clk); @(negedge clk);
  if(valid!==1 || sample!==expected)$fatal(1,"sample mismatch %h %h",sample,expected);
  @(negedge clk);if(valid!==0)$fatal(1,"valid width");
 end endtask
 initial begin repeat(3)@(negedge clk);resetn=1;
 send_word(24'h123456);send_word(24'hfedcba);send_word(24'h000001);send_word(24'h800000);
 repeat(6) begin @(negedge clk);fir_valid=1;@(negedge clk);fir_valid=0;repeat(150)@(negedge clk);end
 if(pcm_count!=2 || overrun!==0)$fatal(1,"FIR decimation count or overrun");
 $display("AUDIO_PASS i2s_samples=4 width=24 fir_inputs=6 pcm16_outputs=2");$finish;end
endmodule
