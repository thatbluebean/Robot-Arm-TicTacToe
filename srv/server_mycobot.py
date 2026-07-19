"""
server_mycobot.py
Runs ON the myCobot 280-Pi (the Raspberry Pi bolted to the arm).

Listens on a TCP socket for JSON gesture commands sent by the laptop
client (client_hand_gesture.py) and translates them into pymycobot calls.

Start this once and leave it running (e.g. as a systemd service, or just
in a `screen`/`tmux` session over SSH). It keeps a single persistent
connection to the arm instead of reconnecting per command.

Usage:
    python3 server_mycobot.py                # talks to the real arm
    python3 server_mycobot.py --simulate      # no hardware needed, just prints actions
"""

import argparse
import json
import socket
import threading
import time

# ----------------------------------------------------------------------
# Configuration - tune these for your setup
# ----------------------------------------------------------------------
HOST = "0.0.0.0"        # listen on all interfaces (reachable over the ethernet link)
PORT = 6000

SERIAL_PORT = "/dev/ttyAMA0"   # default onboard serial port for the 280-Pi; verify with your unit
BAUD_RATE = 1000000

JOG_STEP_DEG = 5          # degrees moved per "point" jog command
JOG_JOINT_MOVED = 1        # which joint index (1-6) the point gesture jogs; change/expand as desired
MOVE_SPEED = 40            # 0-100, keep low while testing
MIN_SECONDS_BETWEEN_MOVES = 0.25   # cooldown so gestures can't spam the arm

GRIPPER_OPEN_VALUE = 100
GRIPPER_CLOSED_VALUE = 0
GRIPPER_SPEED = 50

HOME_ANGLES = [0, 0, 0, 0, 0, 135]
HOME_SPEED = 40
MIN_SECONDS_BETWEEN_HOME = 1.0  # separate, longer cooldown since this is a bigger move

# Joint 2 is the up/down joint per DIRECTION_JOINT below. Clamped so the arm
# can't jog itself into the table (or over-extend upward) via gestures.
# NOTE: if "down" on your physical arm actually corresponds to positive
# angles instead of negative, swap these two values.
VERTICAL_JOINT_UP_LIMIT = 90
VERTICAL_JOINT_DOWN_LIMIT = -90
JOINT_LIMITS = {2: (VERTICAL_JOINT_DOWN_LIMIT, VERTICAL_JOINT_UP_LIMIT)}  # {joint_number: (min_deg, max_deg)}

MIN_SECONDS_BETWEEN_PEACE = 1.0  # cooldown for the "swing straight down" gesture

# Direction -> which joint / sign to move. This is a simple starting mapping;
# expand to control different joints per direction once the single-joint
# version is confirmed working and safe.
DIRECTION_SIGN = {
    "up": +1,
    "down": -1,
    "left": +1,
    "right": -1,
}
DIRECTION_JOINT = {
    "up": 2,
    "down": 2,
    "left": 1,
    "right": 1,
}


class ArmController:
    """Wraps pymycobot so the rest of the server doesn't care whether
    we're running against real hardware or a simulated stand-in."""

    def __init__(self, simulate: bool):
        self.simulate = simulate
        self._last_move_time = 0.0
        self._last_home_time = 0.0
        self._last_peace_time = 0.0
        self._lock = threading.Lock()

        if simulate:
            print("[server] SIMULATE mode: no hardware connection will be made.")
            self.mc = None
        else:
            from pymycobot.mycobot import MyCobot  # imported here so --simulate works with no arm library installed
            print(f"[server] Connecting to arm on {SERIAL_PORT} @ {BAUD_RATE}...")
            self.mc = MyCobot(SERIAL_PORT, BAUD_RATE)
            time.sleep(1)
            print("[server] Connected.")

    def _cooldown_ok(self) -> bool:
        return (time.time() - self._last_move_time) >= MIN_SECONDS_BETWEEN_MOVES

    def gripper_open(self):
        with self._lock:
            print("[arm] gripper -> OPEN")
            if not self.simulate:
                self.mc.set_gripper_value(GRIPPER_OPEN_VALUE, GRIPPER_SPEED)

    def gripper_close(self):
        with self._lock:
            print("[arm] gripper -> CLOSE")
            if not self.simulate:
                self.mc.set_gripper_value(GRIPPER_CLOSED_VALUE, GRIPPER_SPEED)

    def jog(self, direction: str):
        with self._lock:
            if not self._cooldown_ok():
                print(f"[arm] jog '{direction}' ignored (cooldown)")
                return
            joint = DIRECTION_JOINT.get(direction)
            sign = DIRECTION_SIGN.get(direction)
            if joint is None:
                print(f"[arm] unknown direction '{direction}', ignoring")
                return
            if not self.simulate:
                current = self.mc.get_angles()
                if current and len(current) >= joint:
                    target_angle = current[joint - 1] + sign * JOG_STEP_DEG
                    if joint in JOINT_LIMITS:
                        low, high = JOINT_LIMITS[joint]
                        clamped = max(low, min(high, target_angle))
                        if clamped != target_angle:
                            print(f"[arm] jog clamped: joint {joint} target {target_angle:.1f} -> {clamped:.1f}")
                        target_angle = clamped
                    print(f"[arm] jog joint {joint} -> {target_angle:.1f} deg (direction={direction})")
                    current[joint - 1] = target_angle
                    self.mc.send_angles(current, MOVE_SPEED)
            else:
                print(f"[arm] jog joint {joint} by {sign * JOG_STEP_DEG} deg (direction={direction}) [simulated]")
            self._last_move_time = time.time()

    def go_straight_down(self):
        with self._lock:
            if (time.time() - self._last_peace_time) < MIN_SECONDS_BETWEEN_PEACE:
                print("[arm] straight-down ignored (cooldown)")
                return
            vertical_joint = 2  # same joint used for up/down jogging
            print(f"[arm] PEACE SIGN -> swinging joint {vertical_joint} to {VERTICAL_JOINT_DOWN_LIMIT} deg, "
                  f"other joints unchanged")
            if not self.simulate:
                current = self.mc.get_angles()
                if current and len(current) >= vertical_joint:
                    current[vertical_joint - 1] = VERTICAL_JOINT_DOWN_LIMIT
                    self.mc.send_angles(current, MOVE_SPEED)
            self._last_peace_time = time.time()

    def go_home(self):
        with self._lock:
            if (time.time() - self._last_home_time) < MIN_SECONDS_BETWEEN_HOME:
                print("[arm] home ignored (cooldown)")
                return
            print(f"[arm] HOME -> {HOME_ANGLES}")
            if not self.simulate:
                self.mc.send_angles(HOME_ANGLES, HOME_SPEED)
            self._last_home_time = time.time()

    def stop(self):
        with self._lock:
            print("[arm] STOP")
            if not self.simulate:
                self.mc.stop()


def handle_client(conn: socket.socket, addr, arm: ArmController):
    print(f"[server] client connected from {addr}")
    buffer = b""
    with conn:
        conn.settimeout(5.0)
        while True:
            try:
                chunk = conn.recv(1024)
            except socket.timeout:
                continue
            except (ConnectionResetError, OSError):
                break
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    print(f"[server] bad message: {line!r}")
                    continue
                dispatch(msg, arm)
    print(f"[server] client {addr} disconnected")


def dispatch(msg: dict, arm: ArmController):
    gesture = msg.get("gesture")
    if gesture == "fist":
        arm.gripper_close()
    elif gesture == "open_palm":
        arm.gripper_open()
    elif gesture == "point":
        direction = msg.get("direction", "")
        arm.jog(direction)
    elif gesture == "home":
        arm.go_home()
    elif gesture == "peace":
        arm.go_straight_down()
    elif gesture == "none":
        pass  # no hand detected / no confident gesture -> do nothing
    elif gesture == "stop":
        arm.stop()
    else:
        print(f"[server] unrecognized gesture message: {msg}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulate", action="store_true",
                         help="Run without connecting to real hardware (for testing the pipeline).")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()

    arm = ArmController(simulate=args.simulate)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, args.port))
        srv.listen(1)
        print(f"[server] listening on {HOST}:{args.port} (simulate={args.simulate})")
        try:
            while True:
                conn, addr = srv.accept()
                t = threading.Thread(target=handle_client, args=(conn, addr, arm), daemon=True)
                t.start()
        except KeyboardInterrupt:
            print("\n[server] shutting down")


if __name__ == "__main__":
    main()
