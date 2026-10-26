// Reuses the independently tested WM8960/I2S/FIR chain, now at PS FCLK0=100 MHz.
module audio_reset_release(input clk,input async_n,output rst_n);
    (* ASYNC_REG="TRUE" *) reg [1:0] pipe;
    always @(posedge clk or negedge async_n)
        if(!async_n) pipe<=0;else pipe<={pipe[0],1'b1};
    assign rst_n=pipe[1];
endmodule

module audio_pcm_core(
    input clk,input rst_n,input clock_locked,input restart,
    input line_input,input [1:0] gain,
    input aud_bclk,input aud_lrc,input aud_adcdat,
    output aud_dacdat,output aud_scl,inout aud_sda,
    output cfg_ready,output nack,output fir_overrun,
    output pcm_valid,output signed [15:0] pcm
);
    reg [19:0] startup;
    reg audio_async_n;
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin startup<=0;audio_async_n<=0;end
        else if(!clock_locked || restart) begin startup<=0;audio_async_n<=0;end
        else begin
            if(startup<999999) startup<=startup+1'b1;
            audio_async_n<=startup==999999;
        end
    end
    wire sys_n,bclk_n;
    audio_reset_release rs(clk,audio_async_n,sys_n);
    audio_reset_release rb(aud_bclk,audio_async_n,bclk_n);
    wire done,nack_raw;
    wm8960_config #(.CLK_FREQ(100000000)) codec(
        .clk(clk),.rst_n(sys_n),.mic_gain(gain),.line_input(line_input),
        .cfg_done(done),.nack_seen(nack_raw),.aud_scl(aud_scl),.aud_sda(aud_sda));
    (* ASYNC_REG="TRUE" *) reg [1:0] done_sys,nack_sys,done_audio;
    always @(posedge clk or negedge sys_n)
        if(!sys_n) begin done_sys<=0;nack_sys<=0;end
        else begin done_sys<={done_sys[0],done};nack_sys<={nack_sys[0],nack_raw};end
    always @(posedge aud_bclk or negedge bclk_n)
        if(!bclk_n) done_audio<=0;else done_audio<={done_audio[0],done};
    assign cfg_ready=done_sys[1];assign nack=nack_sys[1];
    wire rx_done;wire [23:0] adc_data;
    reg [23:0] mono;reg toggle;
    audio_receive #(.WL(24)) rx(.rst_n(bclk_n),.aud_bclk(aud_bclk),
        .aud_lrc(aud_lrc),.aud_adcdat(aud_adcdat),.rx_done(rx_done),.adc_data(adc_data));
    always @(posedge aud_bclk or negedge bclk_n) begin
        if(!bclk_n) begin mono<=0;toggle<=0;end
        else if(rx_done && !aud_lrc && done_audio[1]) begin mono<=adc_data;toggle<=~toggle;end
    end
    // Keep playback silent to avoid acoustic feedback while measuring speech.
    assign aud_dacdat=1'b0;
    // Stable bundled data, with >=2 destination cycles after the toggle.
    (* ASYNC_REG="TRUE" *) reg [2:0] sync_toggle;
    reg seen,valid48;reg signed [15:0] pcm48;
    always @(posedge clk or negedge sys_n) begin
        if(!sys_n) begin sync_toggle<=0;seen<=0;valid48<=0;pcm48<=0;end
        else begin
            sync_toggle<={sync_toggle[1:0],toggle};valid48<=0;
            if(sync_toggle[2]!=seen) begin seen<=sync_toggle[2];pcm48<=mono[23:8];valid48<=1;end
        end
    end
    fir_decimate3 fir(.clk(clk),.rst_n(sys_n),.valid_in(valid48),.sample_in(pcm48),
        .valid_out(pcm_valid),.sample_out(pcm),.overrun(fir_overrun));
endmodule
