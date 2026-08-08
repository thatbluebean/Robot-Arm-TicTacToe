"""
client_hand_gesture.py
Runs ON THE LAPTOP. Captures webcam video, detects hand landmarks with
MediaPipe's HandLandmarker (Tasks API), classifies a small set of
gestures, and streams gesture commands over TCP to server_mycobot.py
running on the myCobot 280-Pi.

Note: MediaPipe removed the old `mp.solutions.hands` API in recent
releases, so this uses the newer Tasks API instead. On first run it will
automatically download the small hand-landmark model file (~8MB) from
Google's public model bucket into the same folder as this script.

Usage:
    python3 client_hand_gesture.py --host 192.168.1.50
    python3 client_hand_gesture.py --host 192.168.1.50 --no-movement   # gripper only, disable step gesture
    python3 client_hand_gesture.py --dry-run                          # no network, just show detection on screen
"""

import argparse
import json
import math
import os
import socket
import time
import urllib.request

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
PORT = 6000

# How long (seconds) a gesture must be held steady before it's sent.
# "point" is kept short so movement stays responsive; the discrete
# grip/home/peace gestures get a longer hold so they don't fire by accident.
GESTURE_HOLD_SECONDS = {
    "fist": 1.0,
    "open_palm": 1.0,
    "home": 1.0,
    "peace": 1.0,
    "point": 0.1,
}
DEFAULT_HOLD_SECONDS = 0.5  # fallback for any gesture not listed above

MODEL_FILENAME = "hand_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)

# Landmark indices (standard 21-point MediaPipe hand model)
WRIST = 0
FINGER_TIPS = {"thumb": 4, "index": 8, "middle": 12, "ring": 16, "pinky": 20}
FINGER_PIPS = {"thumb": 3, "index": 6, "middle": 10, "ring": 14, "pinky": 18}

# Standard hand-skeleton edges, used only for drawing the overlay on screen
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),          # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),          # index
    (5, 9), (9, 10), (10, 11), (11, 12),     # middle
    (9, 13), (13, 14), (14, 15), (15, 16),   # ring
    (13, 17), (17, 18), (18, 19), (19, 20),  # pinky
    (0, 17),                                  # palm
]


def ensure_model(model_path: str):
    if os.path.exists(model_path):
        return
    print(f"[client] downloading hand landmark model to {model_path} ...")
    urllib.request.urlretrieve(MODEL_URL, model_path)
    print("[client] model downloaded.")


def landmark_dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def finger_extended(landmarks, name) -> bool:
    """A finger counts as extended if its tip is farther from the wrist
    than its pip joint is. This is more robust to hand rotation than
    just comparing y-coordinates."""
    wrist = landmarks[WRIST]
    tip = landmarks[FINGER_TIPS[name]]
    pip = landmarks[FINGER_PIPS[name]]
    return landmark_dist(wrist, tip) > landmark_dist(wrist, pip) * 1.1


def classify_gesture(landmarks):
    """Returns (gesture, direction_or_None) based on 21 hand landmarks.
    `landmarks` is a list of objects with .x/.y (normalized 0-1) attributes."""
    extended = {name: finger_extended(landmarks, name) for name in FINGER_TIPS}
    num_extended = sum(extended.values())

    if num_extended <= 1 and not extended["thumb"] and not extended["index"]:
        return "fist", None
    if num_extended >= 4:
        return "open_palm", None
    if (
        extended["thumb"]
        and not extended["index"]
        and not extended["middle"]
        and not extended["ring"]
        and not extended["pinky"]
    ):
        # Thumbs up: thumb extended and clearly above the wrist (pointing up on screen).
        # Checking the vertical position (not just "thumb extended") rules out a fist
        # held with the thumb sticking out sideways.
        wrist = landmarks[WRIST]
        thumb_tip = landmarks[FINGER_TIPS["thumb"]]
        if (wrist.y - thumb_tip.y) > 0.1:  # smaller y = higher up in image coords
            return "home", None
    if extended["index"] and extended["middle"] and not extended["ring"] and not extended["pinky"]:
        return "peace", None
    if extended["index"] and not extended["middle"] and not extended["ring"] and not extended["pinky"]:
        # Pointing: use vector from wrist to index tip to get a direction
        wrist = landmarks[WRIST]
        tip = landmarks[FINGER_TIPS["index"]]
        dx = tip.x - wrist.x
        dy = tip.y - wrist.y  # image coords: y grows downward
        angle = math.degrees(math.atan2(-dy, dx))  # standard math angle, up = +90
        if 45 <= angle <= 135:
            direction = "up"
        elif -135 <= angle <= -45:
            direction = "down"
        elif angle > 135 or angle < -135:
            direction = "left"
        else:
            direction = "right"
        return "point", direction

    return "none", None


def draw_landmarks(frame, landmarks, width, height):
    points = [(int(lm.x * width), int(lm.y * height)) for lm in landmarks]
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, points[a], points[b], (0, 200, 0), 2)
    for x, y in points:
        cv2.circle(frame, (x, y), 4, (0, 0, 255), -1)


class GestureSender:
    """Handles the TCP connection to the Pi. The caller (main loop) is
    responsible for deciding *when* to send -- this class just gets the 
    message onto the wire."""

    def __init__(self, host, port, dry_run=False):
        self.dry_run = dry_run
        self.sock = None
        if not dry_run:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            print(f"[client] connecting to {host}:{port} ...")
            self.sock.connect((host, port))
            print("[client] connected.")

    def send(self, gesture, direction=None):
        msg = {"gesture": gesture}
        if direction:
            msg["direction"] = direction
        self.send_raw(msg)

    def send_raw(self, msg: dict):
        if self.dry_run:
            print(f"[dry-run] would send: {msg}")
        else:
            data = (json.dumps(msg) + "\n").encode("utf-8")
            try:
                self.sock.sendall(data)
            except OSError as e:
                print(f"[client] send failed: {e}")

    def close(self):
        if self.sock:
            self.sock.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.1.50", help="IP address of the myCobot 280-Pi")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--camera", type=int, default=0, help="OpenCV camera index")
    parser.add_argument("--no-movement", action="store_true",
                        help="Disable the pointing/step movement gesture; only fist/open-palm gripper control is sent")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't connect to the arm at all, just show detected gestures on screen")
    args = parser.parse_args()

    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), MODEL_FILENAME)
    ensure_model(model_path)

    base_options = mp_python.BaseOptions(model_asset_path=model_path)
    options = mp_vision.HandLandmarkerOptions(
        base_options=base_options,
        running_mode=mp_vision.RunningMode.VIDEO,
        num_hands=1,
        min_hand_detection_confidence=0.6,
        min_tracking_confidence=0.5,
    )
    detector = mp_vision.HandLandmarker.create_from_options(options)

    sender = GestureSender(args.host, args.port, dry_run=args.dry_run)

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print("[client] ERROR: could not open camera")
        return

    start_time = time.time()
    candidate_key = None       # (gesture, direction) currently being held
    candidate_start_time = 0.0
    fired_for_candidate = False
    
    # Rate limiter for the stepping commands to avoid overwhelming the server buffer
    last_step_time = 0.0
    STEP_INTERVAL = 0.15  # seconds between step commands

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame = cv2.flip(frame, 1)  # mirror for natural selfie-view display
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            timestamp_ms = int((time.time() - start_time) * 1000)
            result = detector.detect_for_video(mp_image, timestamp_ms)

            gesture, direction = "none", None
            if result.hand_landmarks:
                landmarks = result.hand_landmarks[0]
                h, w, _ = frame.shape
                draw_landmarks(frame, landmarks, w, h)
                gesture, direction = classify_gesture(landmarks)

            now = time.time()
            key = (gesture, direction)
            if key != candidate_key:
                candidate_key = key
                candidate_start_time = now
                fired_for_candidate = False

            hold_time = now - candidate_start_time
            required_hold = GESTURE_HOLD_SECONDS.get(gesture, DEFAULT_HOLD_SECONDS)

            # --- Movement Stepping (pointing): Repeatedly sends while held ---
            if gesture == "point" and hold_time >= required_hold and not args.no_movement:
                if now - last_step_time >= STEP_INTERVAL:
                    sender.send(gesture, direction)
                    last_step_time = now

            # --- Discrete gestures (fist/open_palm/home/peace): fire once per held pose ---
            elif gesture not in ("none", "point") and hold_time >= required_hold and not fired_for_candidate:
                sender.send(gesture, direction)
                fired_for_candidate = True

            label = gesture if not direction else f"{gesture} ({direction})"
            if gesture != "none" and hold_time < required_hold:
                label += f"  holding {hold_time:.1f}/{required_hold:.1f}s"
            cv2.putText(frame, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.imshow("Hand Gesture Control", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        sender.close()
        detector.close()


if __name__ == "__main__":
    main()
