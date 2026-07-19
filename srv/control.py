from pymycobot import MyCobot
import curses
import time

mc = MyCobot("/dev/ttyAMA0", 1000000)

print("Waiting for robot...")
time.sleep(4)

SPEED = 60
STEP = 4

angles = [0, 0, 0, 0, 0, 135]

GRIP_OPEN = 100
GRIP_CLOSED = 40
gripper_open = True

mc.send_angles(angles, 40)
mc.set_gripper_value(GRIP_OPEN, 100)

def main(stdscr):
    global gripper_open

    curses.cbreak()
    curses.noecho()
    stdscr.keypad(True)
    stdscr.nodelay(True)

    stdscr.addstr(0, 0, "A/D = Base")
    stdscr.addstr(1, 0, "W/S = Shoulder")
    stdscr.addstr(2, 0, "Space = Gripper")
    stdscr.addstr(3, 0, "Q = Quit")

    while True:
        key = stdscr.getch()

        changed = False

        if key in (ord('h'), ord('H')):
            angles[0] = 0
            angles[1] = 0
            angles[2] = 0
            angles[3] = 0
            angles[4] = 0
            angles[5] = 135
            changed = True

        if key in (ord('k'), ord('K')):
            angles[3] += STEP
            changed= True
        
        if key in (ord('i'), ord('I')):
            angles[3] -= STEP
            changed = True
        if key in (ord('j'), ord('J')):
            angles[4] += STEP
            changed= True
        
        if key in (ord('l'), ord('L')):
            angles[4] -= STEP
            changed = True

        if key in (ord('a'), ord('A')):
            angles[0] += STEP
   #         angles[4] -= STEP
            changed = True

        if key in (ord('d'), ord('D')):
            angles[0] -= STEP
  #          angles[4] += STEP
            changed = True

        if key in (ord('w'), ord('W')):
            angles[1] -= STEP
 #           angles[3] += STEP
            changed = True

        if key in (ord('s'), ord('S')):
            angles[1] += STEP
#            angles[3] -= STEP
            changed = True

        if key in (ord('q'), ord('Q')):
            angles[5] -= STEP
            changed = True

        if key in (ord('e'), ord('E')):
            angles[5] += STEP
            changed = True

        if key == ord(' '):
            gripper_open = not gripper_open
            if gripper_open:
                mc.set_gripper_value(GRIP_OPEN, 100)
            else:
                mc.set_gripper_value(GRIP_CLOSED, 100)
            time.sleep(0.2)
            
        elif key in (ord('c'), ord('C')):
            break

        angles[0] = max(-170, min(170, angles[0]))
        angles[1] = max(-135, min(135, angles[1]))
        angles[3] = max(-165, min(165, angles[3]))
        angles[5] = max(-180, min(180, angles[5]))
        angles[4] = max(-120, min(120, angles[4]))
        
        if changed:
            mc.send_angles(angles, SPEED)

        stdscr.addstr(5, 0, f"Base:     {angles[0]:4d}   ")
        stdscr.addstr(6, 0, f"Shoulder: {angles[1]:4d}   ")
        stdscr.refresh()

        time.sleep(0.02)

curses.wrapper(main)