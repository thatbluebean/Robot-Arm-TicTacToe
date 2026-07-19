from pymycobot import MyCobot
import time

mc = MyCobot("/dev/ttyAMA0", 1000000)

print('inital loading wait...')
time.sleep(4)
#mc.power_on()

speed = 1000   # maximum


back = [
    0,   
    90,  
    45,  
    0,   
    0,
    135
]

forward = [
    0,    
    8,    
    0,    
    0,    
    0,
    135
]

time.sleep(3)
# mc.send_angles([90,90,0,0,0,0], 75)
print('back')
mc.send_angles(back, 25)
print('wait')
time.sleep(10)
print('forward')
mc.send_angles(forward,100)
time.sleep(5)
