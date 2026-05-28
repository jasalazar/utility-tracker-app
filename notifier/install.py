#!/usr/bin/env python3
"""
macOS LaunchAgent installer for the Utility Tracker notifier daemon.

Usage:
    python notifier/install.py          # Install and load
    python notifier/install.py unload   # Stop and remove

What it does:
  1. Writes a .plist to ~/Library/LaunchAgents/
  2. Calls `launchctl load` to start the daemon immediately
  3. The daemon auto-starts on every login
"""

import os
import subprocess
import sys
from pathlib import Path

PLIST_NAME = "com.utilitytracker.notifier.plist"
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
PLIST_PATH = LAUNCH_AGENTS_DIR / PLIST_NAME

# Resolve absolute paths at install time.
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DAEMON_SCRIPT = PROJECT_ROOT / "notifier" / "daemon.py"
PYTHON_BIN = sys.executable
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
LOG_DIR = Path.home() / "Library" / "Logs" / "UtilityTracker"


PLIST_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.utilitytracker.notifier</string>

    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>{script}</string>
    </array>

    <key>EnvironmentVariables</key>
    <dict>
        <key>REDIS_URL</key>
        <string>{redis_url}</string>
    </dict>

    <!-- Auto-restart if the daemon exits or crashes -->
    <key>KeepAlive</key>
    <true/>

    <!-- Start at login -->
    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>{log_dir}/notifier.log</string>

    <key>StandardErrorPath</key>
    <string>{log_dir}/notifier.error.log</string>

    <!-- Throttle restarts on repeated crashes -->
    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
"""


def install() -> None:
    if not DAEMON_SCRIPT.exists():
        print(f"Error: daemon script not found at {DAEMON_SCRIPT}")
        sys.exit(1)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)

    plist_content = PLIST_TEMPLATE.format(
        python=str(PYTHON_BIN),
        script=str(DAEMON_SCRIPT),
        redis_url=REDIS_URL,
        log_dir=str(LOG_DIR),
    )

    PLIST_PATH.write_text(plist_content)
    print(f"Wrote plist to {PLIST_PATH}")

    # Unload first in case a previous version is running.
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)

    result = subprocess.run(
        ["launchctl", "load", str(PLIST_PATH)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"launchctl load failed: {result.stderr}")
        sys.exit(1)

    print("Notifier daemon installed and started.")
    print(f"Logs: {LOG_DIR}/notifier.log")


def unload() -> None:
    if not PLIST_PATH.exists():
        print(f"Plist not found at {PLIST_PATH} — nothing to unload.")
        return

    result = subprocess.run(
        ["launchctl", "unload", str(PLIST_PATH)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"launchctl unload failed: {result.stderr}")
    else:
        print("Daemon stopped.")

    PLIST_PATH.unlink(missing_ok=True)
    print(f"Removed {PLIST_PATH}")


def status() -> None:
    """Print the current daemon status from launchctl."""
    result = subprocess.run(
        ["launchctl", "list", "com.utilitytracker.notifier"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("Daemon is NOT loaded (launchctl returned non-zero).")
    else:
        print(result.stdout)

    print(f"\nLog files:")
    out_log = LOG_DIR / "notifier.log"
    err_log = LOG_DIR / "notifier.error.log"
    for path in (out_log, err_log):
        if path.exists():
            lines = path.read_text().splitlines()
            print(f"\n--- {path.name} (last 10 lines) ---")
            print("\n".join(lines[-10:]))
        else:
            print(f"\n{path.name}: (not found)")


def test_notification() -> None:
    """
    Publish a test notification directly to Redis so you can verify the
    daemon receives it and displays a macOS Notification Centre alert —
    without waiting for a scheduled payment reminder.

    Usage:
        REDIS_URL=redis://localhost:6379/0 python notifier/install.py test <uid>
    """
    if len(sys.argv) < 3:
        print("Usage: python notifier/install.py test <uid>")
        print("\nYour uid can be found at http://localhost:8000/auth/me")
        sys.exit(1)

    uid = sys.argv[2]
    channel = f"notify:{uid}"

    try:
        import redis as redis_lib
        import json
        r = redis_lib.from_url(REDIS_URL, decode_responses=True)
        r.ping()
    except Exception as exc:
        print(f"Cannot connect to Redis at {REDIS_URL}: {exc}")
        sys.exit(1)

    payload = json.dumps({
        "title": "Utility Tracker — Test",
        "subtitle": "Daemon is working ✓",
        "body": f"Published to {channel}",
    })
    receivers = r.publish(channel, payload)
    print(f"Published test notification to '{channel}' — {receivers} receiver(s) got it.")
    if receivers == 0:
        print("WARNING: 0 receivers. The daemon may not be running or is subscribed to a different channel.")
        print(f"Run: python notifier/install.py status")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "install"
    if command == "unload":
        unload()
    elif command == "status":
        status()
    elif command == "test":
        test_notification()
    else:
        install()
