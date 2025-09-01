from machine import Pin
import time
import rp2

# Serial port, clock stall low
clk = Pin(27, Pin.OUT)
io = Pin(26, Pin.IN)

pdclk = Pin(22, Pin.IN)

d17 = Pin(17, Pin.OUT)
d16 = Pin(16, Pin.OUT)
d15 = Pin(15, Pin.OUT)
d14 = Pin(14, Pin.OUT)

d17(0)
d16(0)
d15(0)
d14(0)

# Verify that:
# - high level sticks
# - low level sticks
def is_bus_idle():
	io.init(Pin.IN, pull=Pin.PULL_UP)
	if not io():
		return False

	# RP2350 bug: very degraded pull-down
	# Briefly switch into output mode to drive low
	# Hopefully it will keep low
	io.init(Pin.OUT)
	io(0)
	io.init(Pin.IN, pull=Pin.PULL_DOWN)

	if io():
		return False

	return True

# Most Significant Bit First
# Ensure no bus conflict
def serial_write(byte):
	assert is_bus_idle()

	io.init(Pin.OUT)

	for i in range(8):
		clk(0)
		io(byte & 0x80 >> i > 0)
		clk(1)

	clk(0)

def serial_read():
	io.init(Pin.IN)
	result = 0x00

	for i in range(8):
		clk(1)
		result += result + io()
		clk(0)

	return result

def read_reg(n, width=8):
	serial_write(0x80 + n)
	positions = []

	for i in range(width):
		positions.append(f"{serial_read():02x}")

	print(" ".join(positions))

def to_ftw(freq, sysclk=25*1000*1000):
	fstep = sysclk/(2**32)
	return round(freq / fstep).to_bytes(4, "big")

# Write register 0
serial_write(0x00)
serial_write(0x00)
serial_write(0x20) # Clear CCI - this is important; one may get junk out of it otherwise
serial_write(0x00)
serial_write(0x00)

# Write register 1
serial_write(0x01)
serial_write(0x00)
serial_write(0x40)
serial_write(0x38) # Parallel port DDR mode (PDCLK = 1/2 baseband clk, rise/fall latching) + data format: offset binary
serial_write(0x00)

# Write register 2
#
# For now commented out
#
# Some current draw figures
# Setup: continuous tone at 100 kHz, 30 mA FSC, CCI enabled
# SYSCLK        Multiplier              Current draw
# 25 MHz        1x, No PLL              70 mA
# 500 MHz	20x, VCO1		229 mA
#serial_write(0x02)
#serial_write(0b00001000 + 1) # Enable VCO + Select VCO 1
#serial_write(7 << 3)         # Max charge pump current
#serial_write(0b11000001)     # Divider disable + PLL enable
#serial_write(20 << 1)        # Multiplier of 20

# Write register 3
serial_write(0x03)
serial_write(0x00)
serial_write(0x00)
serial_write(0x00)
serial_write(0xFF) # Full scale current to 30mA (this is safe with 10ohm load)

# Radiate at
ftw = to_ftw(0.1*1000*1000, 25*1000*1000)

# Output enablement
# Touch the profile pins as well as parallel port pins with your finger to make effective
for i in range(8):
	serial_write(0x0E + i) # Profile
	serial_write((40<<2) + 0x01) # 40x Interpolation + Inverse CCI disable
	serial_write(0x80) # Output scale factor (When IQ=all 1s, >0x80 is distortion?)
	serial_write(0x00) # Phase offset = none
	serial_write(0x00) # Phase offset = none
	serial_write( ftw[0] ) # FTW
	serial_write( ftw[1] ) # FTW
	serial_write( ftw[2] ) # FTW
	serial_write( ftw[3] ) # FTW

x = machine.ADC(28)

# Measurements using 3.3V ADC over 3.3ohm shunt
def sample_current(samples=32):
	u_lst = [x.read_u16() for i in range(samples)]
	u = sum(u_lst)/samples / 65535 * 3.3
	return u / 3.3

# Let's run at an I/Q rate of 25 MHz / 4 / 40 to MHz = 0.15625 MHz
# This amounts to passband until 0.0625 MHz
# This program has to push out an IQ word
#
# Quick overview
# https://docs.micropython.org/en/latest/rp2/tutorial/pio.html
#
# Detailed instruction docs
# https://docs.micropython.org/en/latest/library/rp2.html
#
@rp2.asm_pio(
	autopull=True,
	fifo_join=rp2.PIO.JOIN_TX,
	out_init=(
		rp2.PIO.OUT_LOW,
		rp2.PIO.OUT_LOW,
		rp2.PIO.OUT_LOW,
		rp2.PIO.OUT_LOW
	)
)
def modulation():
	wrap_target()
	wait(0, gpio, 22) # I-word
	out(pins, 4)
	wait(1, gpio, 22) # Q-word
	out(pins, 4)
	wrap()

# We have 8x32 bit FIFO
#idle = 0b11111000111110001111100011111000
#acty = 0b11111111111111111111111111111111

# Period of 8
# I-word always at half scale
# Q-word wiggled as hard as possible
idle = 0b10000000100000001000000010000000
acty = 0b10001111100011111000111110001111

"""
# PIO at machine clock
sm = rp2.StateMachine(0, modulation, freq=150*1000*1000, out_base=d14)
sm.put(idle)
sm.put(idle)
sm.put(idle)
sm.put(idle)
sm.put(idle)
sm.put(idle)
sm.put(idle)
sm.put(idle)
sm.active(1)
"""

def baseband_tone(freq):
	sm.init(modulation, freq=freq*2, set_base=d14)
	sm.active(1)

while True:
	i = sample_current()
	print(f"{i*1000:.1f} mA")
	time.sleep(.1)

	#read_reg(0x0E)

	# Alert if we ever underrun
	#assert sm.tx_fifo()
	#sm.put(idle)
	#sm.put(acty)
	#pass
