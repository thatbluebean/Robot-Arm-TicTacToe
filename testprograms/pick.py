from pymycobot import MyCobot
import time

mc = MyCobot("/dev/ttyAMA0", 1000000)

print('inital loading wait...')
time.sleep(4)
#mc.power_on()

speed = 100   # maximum

reset = [0,0,0,0,0,135]

back = [
    0,   
    85,  
    45,  
    0,   
    0,
    135
]

forward = [
    0,    
    -90,    
    0,    
    0,    
    0,
    135
]

print('reset')
mc.send_angles(reset, 100)
time.sleep(2)
mc.set_gripper_value(100, 100)
time.sleep(4)

print('forward')
mc.send_angles(forward, 100)
time.sleep(4)

print('grip')
mc.set_gripper_value(45, 100)
time.sleep(3)

print('back up')
mc.send_angles(reset, 100)
time.sleep(4)

