#!/usr/bin/env python3
import os
import time
import subprocess
import sys
import re
import shutil
import signal

# ==== CONFIG ====
JANUS_DIR = "/home/arratia/Documents/Janus_5202_4.1.2_20250415_linux/bin"
JANUS_PATH = os.path.join(JANUS_DIR, "JanusC")
CONFIG = os.path.join(JANUS_DIR, "Janus_Config.txt")

PTRG_SRC   = "/home/arratia/Documents/ptrg.txt"
TLOGIC_SRC = "/home/arratia/Documents/cosmic.txt"

PTRG_TIME   = 8
TLOGIC_TIME = 600

BOARDS = [0,1,2]
HV_ON_THRESHOLD = 20.0

MODES = [
    ("PTRG",   PTRG_SRC,   PTRG_TIME,   "janus_ptrg"),
    ("TLOGIC", TLOGIC_SRC, TLOGIC_TIME, "janus_tlogic")
]

ACTIVE_SESSION = None   # used for emergency shutdown


# ==== SIGNAL HANDLING ====

def sigint_handler(sig, frame):
    print("\n[!] Ctrl+C detected — forcing HV OFF")
    if ACTIVE_SESSION:
        janus_stop_hv_off(ACTIVE_SESSION)
    sys.exit(130)

signal.signal(signal.SIGINT, sigint_handler)


# ==== UTILS ====

def tmux_session_exists(session):
    return subprocess.run(
        ["tmux", "has-session", "-t", session],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    ).returncode == 0


def sleep_interruptible(seconds):
    t0 = time.time()
    while time.time() - t0 < seconds:
        time.sleep(0.2)


def safe_tmux_send(session, key):
    subprocess.run(
        ["tmux", "send-keys", "-t", session, key, "C-m"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


# ==== JANUS CONTROL ====

def wait_for_tmux(session, timeout=20):
    for _ in range(timeout * 5):
        if tmux_session_exists(session):
            return True
        time.sleep(0.2)
    return False


def get_vmon(session, timeout=5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        out = subprocess.run(
            ["tmux", "capture-pane", "-t", session, "-p"],
            capture_output=True, text=True
        ).stdout
        m = re.search(r"Vmon\s*=\s*([0-9.]+)", out)
        if m:
            return float(m.group(1))
        time.sleep(0.3)
    return None


def select_board(session, board):
    safe_tmux_send(session, "b")
    time.sleep(0.4)
    safe_tmux_send(session, str(board))
    time.sleep(0.4)
    safe_tmux_send(session, "")


# ==== HV CONTROL ====

def ensure_hv_on(session):
    print("[*] Checking HV state...")
    safe_tmux_send(session, "h")
    time.sleep(1)

    for board in BOARDS:
        select_board(session, board)
        time.sleep(1)

        v = get_vmon(session)
        if v is None:
            raise RuntimeError("Cannot read Vmon")

        print(f"    Board {board}: Vmon = {v:.2f} V")

        if v < HV_ON_THRESHOLD:
            print("    HV OFF → ramping ON")
            safe_tmux_send(session, "H")
            time.sleep(2)
        else:
            print("    HV already ON → skipping")

    safe_tmux_send(session, "q")
    print("[*] Waiting 10s for voltage stabilization...")
    sleep_interruptible(10)


def janus_stop_hv_off(session):
    print("[!] Emergency shutdown — HV OFF")

    subprocess.run(["tmux", "send-keys", "-t", session, "S", "C-m"])
    time.sleep(1)
    subprocess.run(["tmux", "send-keys", "-t", session, "q", "C-m"])
    time.sleep(1)
    subprocess.run(["tmux", "send-keys", "-t", session, "y", "C-m"])
    sleep_interruptible(5)

    subprocess.run(["tmux", "kill-session", "-t", session],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("[!] HV shutdown COMPLETE")


def janus_stop_keep_hv_on(session):
    print("[*] Stopping run, keeping HV ON")

    safe_tmux_send(session, "S")
    time.sleep(2)
    safe_tmux_send(session, "q")
    time.sleep(1)
    safe_tmux_send(session, "n")

    sleep_interruptible(3)

    subprocess.run(["tmux", "kill-session", "-t", session],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("[*] Session closed, HV preserved")


def janus_startup(session):
    global ACTIVE_SESSION
    ACTIVE_SESSION = session

    subprocess.run(["tmux", "kill-session", "-t", session],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("[*] Starting Janus...")

    subprocess.run(
        ["tmux", "new-session", "-d", "-s", session, "./JanusC"],
        cwd=JANUS_DIR
    )

    if not wait_for_tmux(session):
        raise RuntimeError("tmux failed to start")

    print("[*] tmux session confirmed alive")
    time.sleep(3)

    ensure_hv_on(session)


def janus_start_recording(session):
    print("[*] Starting recording...")
    safe_tmux_send(session, "s")
    time.sleep(1)


# ==== RUN MODE LOOP ====

def run_mode(name, config_src, duration, session):
    print("="*50)
    print(f"[*] Starting {name}")
    print("="*50)

    shutil.copy(config_src, CONFIG)
    time.sleep(2)

    try:
        janus_startup(session)
        janus_start_recording(session)

        print(f"[*] Recording for {duration}s")

        t0 = time.time()
        while time.time() - t0 < duration:
            sleep_interruptible(0.5)

        janus_stop_keep_hv_on(session)
        print(f"[✓] {name} completed successfully")

    except Exception as e:
        print("[!] ERROR:", e)
        janus_stop_hv_off(session)
        raise


# ==== MAIN LOOP ====

def main():
    while True:
        for mode in MODES:
            run_mode(*mode)


if __name__ == "__main__":
    main()
