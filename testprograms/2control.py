import curses
import time
from pymycobot import MyCobot

# --- Configuration ---
PORT = "/dev/ttyAMA0"
BAUD = 1000000
SPEED = 80
STEP = 6

GRIP_OPEN = 100
GRIP_CLOSED = 7

# Joint angle limits: (min_angle, max_angle)
JOINT_LIMITS = [
    (-170, 170),  # Joint 1 (Base)
    (-90, 90),    # Joint 2 (Shoulder)
    (-180, 180),  # Joint 3
    (-165, 165),  # Joint 4
    (-120, 120),  # Joint 5
    (-180, 180)   # Joint 6
]

# --- Robot Initialization ---
print("Connecting to MyCobot...")
mc = MyCobot(PORT, BAUD)
time.sleep(4)

# Set initial state
angles = [0, 0, 0, 0, 0, 135]
gripper_open = True

mc.send_angles(angles, 40)
mc.set_gripper_value(GRIP_OPEN, 100)


def main(stdscr):
    global gripper_open

    # Curses setup
    curses.cbreak()
    curses.noecho()
    stdscr.keypad(True)
    stdscr.nodelay(True)

    # Key mapping structure: { key_char: (joint_index, direction_multiplier) }
    control_map = {
        'a': (0, 1),  'd': (0, -1),   # Joint 1 (Base)
        'w': (1, -1), 's': (1, 1),    # Joint 2 (Shoulder)
        'r': (3, 1),  'f': (3, -1),   # Joint 4
        't': (4, 1),  'g': (4, -1),   # Joint 5
        'e': (5, 1),  'q': (5, -1),   # Joint 6
    }

    while True:
        # Clear screen and draw menu/telemetry
        stdscr.erase()
        stdscr.addstr(0, 0, "--- MyCobot Curses Controller ---")
        stdscr.addstr(2, 0, "Controls:")
        stdscr.addstr(3, 2, "A / D     : Joint 1 (Base)")
        stdscr.addstr(4, 2, "W / S     : Joint 2 (Shoulder)")
        stdscr.addstr(5, 2, "R / F     : Joint 4")
        stdscr.addstr(6, 2, "T / G     : Joint 5")
        stdscr.addstr(7, 2, "E / Q     : Joint 6")
        stdscr.addstr(8, 2, "SPACEBAR  : Toggle Gripper")
        stdscr.addstr(9, 2, "H         : Reset Home Position")
        stdscr.addstr(10, 2, "C         : Exit Program")

        stdscr.addstr(12, 0, "Current Positions:")
        for i, angle in enumerate(angles):
            stdscr.addstr(13 + i, 2, f"Joint {i+1}: {angle:4d}°")
        
        stdscr.refresh()

        # Handle Input
        try:
            ch = stdscr.getch()
        except Exception:
            ch = -1

        if ch == -1:
            time.sleep(0.02)
            continue

        key_char = chr(ch).lower() if 0 <= ch < 256 else ''
        changed = False

        # 1. Check movement keys
        if key_char in control_map:
            joint_idx, direction = control_map[key_char]
            angles[joint_idx] += STEP * direction
            changed = True

        # 2. Check Home Key
        elif key_char == 'h':
            angles[:] = [0, 0, 0, 0, 0, 135]
            changed = True

        # 3. Check Gripper
        elif ch == ord(' '):
            gripper_open = not gripper_open
            target_grip = GRIP_OPEN if gripper_open else GRIP_CLOSED
            mc.set_gripper_value(target_grip, 100)
            time.sleep(0.2)  # Debounce delay

        # 4. Check Quit Key
        elif key_char == 'c':
            break

        # Apply safety constraints to all joints
        for i in range(len(angles)):
            low, high = JOINT_LIMITS[i]
            angles[i] = max(low, min(high, angles[i]))

        # Send target commands to robot hardware
        if changed:
            mc.send_angles(angles, SPEED)

        time.sleep(0.02)


if __name__ == "__main__":
    curses.wrapper(main)