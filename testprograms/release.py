from pymycobot import MyCobot
import time

mc = MyCobot("/dev/ttyAMA0", 1000000)

print('inital loading wait...')
time.sleep(2)
#mc.power_on()

speed = 100   # maximum

reset = [0,0,0,0,0,135]

print('reset')
mc.send_angles(reset, 50)
time.sleep(2)
mc.set_gripper_value(100, 30)
time.sleep(4)