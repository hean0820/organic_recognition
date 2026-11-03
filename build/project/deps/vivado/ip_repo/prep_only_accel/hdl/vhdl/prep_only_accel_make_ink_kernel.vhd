-- ==============================================================
-- Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2020.2 (64-bit)
-- Copyright 1986-2020 Xilinx, Inc. All Rights Reserved.
-- ==============================================================
library ieee; 
use ieee.std_logic_1164.all; 
use ieee.std_logic_unsigned.all;

entity prep_only_accel_make_ink_kernel_rom is 
    generic(
             DWIDTH     : integer := 4; 
             AWIDTH     : integer := 7; 
             MEM_SIZE    : integer := 67
    ); 
    port (
          addr0      : in std_logic_vector(AWIDTH-1 downto 0); 
          ce0       : in std_logic; 
          q0         : out std_logic_vector(DWIDTH-1 downto 0);
          addr1      : in std_logic_vector(AWIDTH-1 downto 0); 
          ce1       : in std_logic; 
          q1         : out std_logic_vector(DWIDTH-1 downto 0);
          addr2      : in std_logic_vector(AWIDTH-1 downto 0); 
          ce2       : in std_logic; 
          q2         : out std_logic_vector(DWIDTH-1 downto 0);
          clk       : in std_logic
    ); 
end entity; 


architecture rtl of prep_only_accel_make_ink_kernel_rom is 

signal addr0_tmp : std_logic_vector(AWIDTH-1 downto 0); 
signal addr1_tmp : std_logic_vector(AWIDTH-1 downto 0); 
signal addr2_tmp : std_logic_vector(AWIDTH-1 downto 0); 
type mem_array is array (0 to MEM_SIZE-1) of std_logic_vector (DWIDTH-1 downto 0); 
signal mem0 : mem_array := (
    0 to 2=> "0000", 3 => "0001", 4 to 5=> "0000", 6 => "0001", 7 => "0000", 
    8 to 11=> "0001", 12 => "0010", 13 => "0001", 14 => "0011", 15 => "0010", 
    16 to 17=> "0011", 18 to 19=> "0100", 20 to 22=> "0101", 23 => "0110", 24 to 25=> "0111", 
    26 to 28=> "1000", 29 to 32=> "1001", 33 => "1010", 34 to 37=> "1001", 38 to 40=> "1000", 
    41 to 42=> "0111", 43 => "0110", 44 to 46=> "0101", 47 to 48=> "0100", 49 to 50=> "0011", 
    51 => "0010", 52 => "0011", 53 => "0001", 54 => "0010", 55 to 58=> "0001", 
    59 => "0000", 60 => "0001", 61 to 62=> "0000", 63 => "0001", 64 to 66=> "0000" );
signal mem1 : mem_array := (
    0 to 2=> "0000", 3 => "0001", 4 to 5=> "0000", 6 => "0001", 7 => "0000", 
    8 to 11=> "0001", 12 => "0010", 13 => "0001", 14 => "0011", 15 => "0010", 
    16 to 17=> "0011", 18 to 19=> "0100", 20 to 22=> "0101", 23 => "0110", 24 to 25=> "0111", 
    26 to 28=> "1000", 29 to 32=> "1001", 33 => "1010", 34 to 37=> "1001", 38 to 40=> "1000", 
    41 to 42=> "0111", 43 => "0110", 44 to 46=> "0101", 47 to 48=> "0100", 49 to 50=> "0011", 
    51 => "0010", 52 => "0011", 53 => "0001", 54 => "0010", 55 to 58=> "0001", 
    59 => "0000", 60 => "0001", 61 to 62=> "0000", 63 => "0001", 64 to 66=> "0000" );


begin 


memory_access_guard_0: process (addr0) 
begin
      addr0_tmp <= addr0;
--synthesis translate_off
      if (CONV_INTEGER(addr0) > mem_size-1) then
           addr0_tmp <= (others => '0');
      else 
           addr0_tmp <= addr0;
      end if;
--synthesis translate_on
end process;

memory_access_guard_1: process (addr1) 
begin
      addr1_tmp <= addr1;
--synthesis translate_off
      if (CONV_INTEGER(addr1) > mem_size-1) then
           addr1_tmp <= (others => '0');
      else 
           addr1_tmp <= addr1;
      end if;
--synthesis translate_on
end process;

memory_access_guard_2: process (addr2) 
begin
      addr2_tmp <= addr2;
--synthesis translate_off
      if (CONV_INTEGER(addr2) > mem_size-1) then
           addr2_tmp <= (others => '0');
      else 
           addr2_tmp <= addr2;
      end if;
--synthesis translate_on
end process;

p_rom_access: process (clk)  
begin 
    if (clk'event and clk = '1') then
        if (ce0 = '1') then 
            q0 <= mem0(CONV_INTEGER(addr0_tmp)); 
        end if;
        if (ce1 = '1') then 
            q1 <= mem0(CONV_INTEGER(addr1_tmp)); 
        end if;
        if (ce2 = '1') then 
            q2 <= mem1(CONV_INTEGER(addr2_tmp)); 
        end if;
    end if;
end process;

end rtl;

Library IEEE;
use IEEE.std_logic_1164.all;

entity prep_only_accel_make_ink_kernel is
    generic (
        DataWidth : INTEGER := 4;
        AddressRange : INTEGER := 67;
        AddressWidth : INTEGER := 7);
    port (
        reset : IN STD_LOGIC;
        clk : IN STD_LOGIC;
        address0 : IN STD_LOGIC_VECTOR(AddressWidth - 1 DOWNTO 0);
        ce0 : IN STD_LOGIC;
        q0 : OUT STD_LOGIC_VECTOR(DataWidth - 1 DOWNTO 0);
        address1 : IN STD_LOGIC_VECTOR(AddressWidth - 1 DOWNTO 0);
        ce1 : IN STD_LOGIC;
        q1 : OUT STD_LOGIC_VECTOR(DataWidth - 1 DOWNTO 0);
        address2 : IN STD_LOGIC_VECTOR(AddressWidth - 1 DOWNTO 0);
        ce2 : IN STD_LOGIC;
        q2 : OUT STD_LOGIC_VECTOR(DataWidth - 1 DOWNTO 0));
end entity;

architecture arch of prep_only_accel_make_ink_kernel is
    component prep_only_accel_make_ink_kernel_rom is
        port (
            clk : IN STD_LOGIC;
            addr0 : IN STD_LOGIC_VECTOR;
            ce0 : IN STD_LOGIC;
            q0 : OUT STD_LOGIC_VECTOR;
            addr1 : IN STD_LOGIC_VECTOR;
            ce1 : IN STD_LOGIC;
            q1 : OUT STD_LOGIC_VECTOR;
            addr2 : IN STD_LOGIC_VECTOR;
            ce2 : IN STD_LOGIC;
            q2 : OUT STD_LOGIC_VECTOR);
    end component;



begin
    prep_only_accel_make_ink_kernel_rom_U :  component prep_only_accel_make_ink_kernel_rom
    port map (
        clk => clk,
        addr0 => address0,
        ce0 => ce0,
        q0 => q0,
        addr1 => address1,
        ce1 => ce1,
        q1 => q1,
        addr2 => address2,
        ce2 => ce2,
        q2 => q2);

end architecture;


