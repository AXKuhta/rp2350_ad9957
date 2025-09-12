from time import time
import usb1

import matplotlib.pyplot as plt
import numpy as np

# ffmpeg -i audio.mp3 -ac 1 -ar 156250 -f f32le test.f32
with open("test.f32", "rb") as f:
	data = bytearray(f.read())

freq = np.frombuffer(data[:156250*4*60], np.float32)
phase = np.cumsum(freq)/156250 * 2 * np.pi * 2500 # Default NFM deviation of 2.5 kHz in SDRAngel

#plt.plot(phase)
#plt.show()

#
# We operate with a baseband of:
# 25 MHz / 4 / 40 = 156.25 kHz
#
# Passband is ±0.4
# So, ±62.5 kHz
#

# Radiate for 5 seconds
t = np.linspace(0, 5, 156250 * 5)

# Seem to be limited to ±8 kHz in reality
# Add more subcarriers as you wish,
# but be sure to scale accordingly
#x = np.exp(1j * 2 * np.pi * t * -1*1000)
x = np.exp(1j * phase)

#plt.plot(x.real)
#plt.plot(x.imag)
#plt.show()

# Format as offset binary, bit depth of 4
s = 8*x + 8 + 8j
u = np.uint16(s.real)
v = np.uint16(s.imag)

u = np.clip(u, 0, 15)
v = np.clip(v, 0, 15)

#plt.step(t, u)
#plt.step(t, v)
#plt.show()

sequence = bytes(k + (l<<4) for k, l in zip(u, v))

ctx = usb1.USBContext()
handle = None

print ("VID  PID")

for dev in ctx.getDeviceList():
	vid = dev.getVendorID()
	pid = dev.getProductID()
	print(f"{vid:04x} {pid:04x}")
	if vid == 0xCAFE and pid == 0x4011:
		print("Device found")
		handle = dev.open()

handle.claimInterface(2)

EP = 0x03

start = time()

handle.bulkWrite(EP, sequence, timeout=60*1000)

elapsed = time() - start
count = len(sequence)
rate = count/elapsed
kibi = rate/1024

print(f"{kibi:.1f}kB/s")
