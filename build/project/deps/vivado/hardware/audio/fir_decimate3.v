// Causal 127-tap anti-alias filter, 48 kHz -> 16 kHz. Signed PCM16, Q17 taps.
// One sequential MAC; final saturation has its own cycle for 100 MHz timing.
// Input interval must exceed 129 clocks (48 kHz at 100 MHz gives ~2083).
module fir_decimate3(
    input clk, input rst_n, input valid_in, input signed [15:0] sample_in,
    output reg valid_out, output reg signed [15:0] sample_out,
    output reg overrun
);
    reg signed [15:0] history [0:126];
    reg [6:0] wr_ptr, rd_ptr, tap;
    reg [1:0] phase;
    reg busy;
    reg signed [47:0] accumulator;
    reg signed [47:0] final_sum;
    reg finish_pending;
    integer k;
    function signed [17:0] coefficient;
        input [6:0] index;
        begin
            case (index)
`include "fir_coefficients.vh"
                default: coefficient=0;
            endcase
        end
    endfunction
    wire signed [33:0] product = $signed(history[rd_ptr]) * coefficient(tap);
    wire signed [47:0] sum = accumulator + {{14{product[33]}},product};
    wire signed [47:0] scaled = final_sum >>> 17;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_ptr<=0; rd_ptr<=0; tap<=0; phase<=0; busy<=0;
            accumulator<=0; final_sum<=0;finish_pending<=0;valid_out<=0; sample_out<=0; overrun<=0;
            for (k=0;k<127;k=k+1) history[k]<=0;
        end else begin
            valid_out<=0;
            if(finish_pending) begin
                finish_pending<=0;valid_out<=1;
                if (scaled>32767) sample_out<=16'sh7fff;
                else if (scaled < -32768) sample_out<=16'sh8000;
                else sample_out<=scaled[15:0];
            end
            if (valid_in) begin
                if (busy) overrun<=1;
                else begin
                    history[wr_ptr]<=sample_in;
                    wr_ptr <= wr_ptr==126 ? 0 : wr_ptr+1'b1;
                    if (phase==2) begin
                        phase<=0; rd_ptr<=wr_ptr; tap<=0; accumulator<=0; busy<=1;
                    end else phase<=phase+1'b1;
                end
            end
            if (busy) begin
                accumulator<=sum;
                rd_ptr<=rd_ptr==0 ? 126 : rd_ptr-1'b1;
                if (tap==126) begin
                    busy<=0;final_sum<=sum;finish_pending<=1;
                end else tap<=tap+1'b1;
            end
        end
    end
endmodule
