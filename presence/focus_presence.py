"""Show the current focus block as Discord Rich Presence ("Focus: ..." with a countdown).

Plain code only, no model: Claude already decided the focus blocks when it wrote them to
the calendar; switching the presence at their start and end is mechanical. Runs while
logged in (Discord is per user), checks the calendar every few minutes, and talks to the
Discord desktop client through discord_relay.ps1, since WSL can't open its named pipe.

Usage:  .venv/bin/python presence/focus_presence.py          # keep running
        .venv/bin/python presence/focus_presence.py --once   # set or clear once, then exit
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "calendar_mcp"))

from gcal import TZ, day_events  # noqa: E402

RELAY = ROOT / "presence" / "discord_relay.ps1"
LOG_FILE = ROOT / "logs" / "presence.log"
CHECK_EVERY = 30  # seconds between checks of the current block
REFRESH_EVERY = 300  # seconds between calendar reads


def log(message: str) -> None:
    LOG_FILE.parent.mkdir(exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")


def current_block(events: list[dict], now: datetime) -> dict | None:
    """The [claude] event happening now, if any."""
    for e in events:
        if e["claude"] and not e["all_day"]:
            if datetime.fromisoformat(e["start"]) <= now < datetime.fromisoformat(e["end"]):
                return e
    return None


def activity(block: dict) -> dict:
    start, end = datetime.fromisoformat(block["start"]), datetime.fromisoformat(block["end"])
    span = f"{start:%-I:%M} to {end:%-I:%M %p}"
    topic = re.sub(r"^\s*focus( block)?\s*[:\-]\s*", "", block["title"], flags=re.I) or block["title"]
    return {"details": f"Focus Block: {topic}", "state": span,
            "timestamps": {"start": int(start.timestamp()), "end": int(end.timestamp())}}


class Discord:
    """One relay process = one connection to the Discord client."""

    def __init__(self, client_id: str):
        self.client_id = client_id
        self.proc = None
        self.pid = None

    def _start(self) -> None:
        win_path = subprocess.run(["wslpath", "-w", str(RELAY)], capture_output=True,
                                  text=True, check=True).stdout.strip()
        self.proc = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", win_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self.pid = json.loads(self.proc.stdout.readline())["pid"]
        reply = self._send(0, {"v": 1, "client_id": self.client_id})
        if reply.get("evt") != "READY":
            raise RuntimeError(f"Discord handshake failed: {reply}")

    def _send(self, op: int, data: dict) -> dict:
        self.proc.stdin.write(json.dumps({"op": op, "data": data}) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("relay exited (is Discord running?)")
        return json.loads(line)

    def set(self, act: dict | None) -> None:
        if self.proc is None or self.proc.poll() is not None:
            self._start()
        args = {"pid": self.pid, "activity": act}
        reply = self._send(1, {"cmd": "SET_ACTIVITY", "args": args, "nonce": uuid.uuid4().hex})
        if reply.get("evt") == "ERROR":
            raise RuntimeError(f"Discord rejected the activity: {reply.get('data')}")

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    client_id = os.getenv("DISCORD_CLIENT_ID")
    if not client_id:
        sys.exit("Set DISCORD_CLIENT_ID in .env (Discord developer portal > your app > Application ID)")

    discord = Discord(client_id)
    events, read_at, shown, last_error = [], 0.0, "unset", None
    while True:
        block = None
        try:
            if time.time() - read_at > REFRESH_EVERY:
                events, read_at = day_events(datetime.now(TZ).date()), time.time()
            block = current_block(events, datetime.now(TZ))
            key = block["id"] if block else None
            if key != shown:
                discord.set(activity(block) if block else None)
                log(f"presence: {block['title'] if block else 'cleared'}")
                shown, last_error = key, None
        except Exception as e:
            if str(e) != last_error:  # e.g. Discord closed: log once, keep retrying quietly
                log(f"error: {e}")
                last_error = str(e)
            discord.close()
            discord, shown = Discord(client_id), "unset"
        if args.once:
            if block:
                input("Presence set. Press Enter to clear it and exit...")
            discord.close()
            return
        time.sleep(CHECK_EVERY)


if __name__ == "__main__":
    main()
